"""Speech-to-text service (faster-whisper, CPU, int8). Internal only: no authentication, no published port.

POST /transcribe (multipart): `audio` (<= 2 MB, <= 30 s), optional `language` (uz | ru | auto), optional `prompt` (vocabulary hint; `prompt_uz` / `prompt_ru` are used for that language). Language auto-detection chooses only between Turkic (= Uzbek) and Russian.
No audio is written to disk and no recognised text is ever logged.
"""
from __future__ import annotations

import asyncio
import io
import logging
import math
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

MODEL_NAME = os.environ.get("WHISPER_MODEL", "base")
COMPUTE = os.environ.get("WHISPER_COMPUTE", "int8")
DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
MAX_BYTES = int(os.environ.get("WHISPER_MAX_BYTES", str(2 * 1024 * 1024)))
MAX_SECONDS = float(os.environ.get("WHISPER_MAX_SECONDS", "30"))
CONCURRENCY = max(1, int(os.environ.get("WHISPER_CONCURRENCY", "1")))
QUEUE = max(0, int(os.environ.get("WHISPER_QUEUE", "2")))  # requests allowed to wait besides the running ones
LANGUAGES = {"uz", "ru"}

logging.basicConfig(level=logging.INFO, format='{"t":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}')
log = logging.getLogger("whisper")

state: dict = {"model": None}
gate = asyncio.Semaphore(CONCURRENCY)
waiting = 0


@asynccontextmanager
async def lifespan(_: FastAPI):
    from faster_whisper import WhisperModel

    t0 = time.perf_counter()
    state["model"] = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE, download_root="/models", cpu_threads=int(os.environ.get("OMP_NUM_THREADS", "2")))
    log.info("model %s loaded in %.1fs", MODEL_NAME, time.perf_counter() - t0)
    yield


app = FastAPI(title="toir-whisper", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "model": MODEL_NAME, "loaded": state["model"] is not None}


def _confidence(segments: list, language_probability: float | None) -> float | None:
    """Mean of the segments' exp(avg_logprob) (the average token probability, 0..1); falls back to the language probability."""
    values = [math.exp(s.avg_logprob) for s in segments if s.avg_logprob is not None]
    if values:
        return round(max(0.0, min(1.0, sum(values) / len(values))), 3)
    return None if language_probability is None else round(float(language_probability), 3)


TURKIC = {"uz", "tr", "kk", "az", "tk", "ky", "tt", "ba"}  # what a small model calls Uzbek when it is unsure


def _pick_language(model, audio) -> str:
    """Auto mode for TWO languages only: the Turkic languages together against Russian (a short Uzbek clip is often labelled Turkish/Kazakh)."""
    _lang, _prob, all_probs = model.detect_language(audio)
    probs = dict(all_probs)
    turkic = sum(p for code, p in probs.items() if code in TURKIC)
    return "uz" if turkic >= probs.get("ru", 0.0) else "ru"


def _run(data: bytes, language: str | None, prompts: dict[str, str]) -> dict:
    from faster_whisper.audio import decode_audio

    model = state["model"]
    audio = decode_audio(io.BytesIO(data), sampling_rate=16000)
    duration = len(audio) / 16000.0
    if duration > MAX_SECONDS + 0.5:
        raise ValueError("too_long")
    chosen = language or _pick_language(model, audio)
    segments_iter, _info = model.transcribe(
        audio,
        language=chosen,
        task="transcribe",
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=False,
        initial_prompt=(prompts.get(chosen) or prompts.get("") or None),
        temperature=0.0,
    )
    segments = list(segments_iter)
    text = " ".join(s.text.strip() for s in segments).strip()
    return {"text": text, "language": chosen, "confidence": _confidence(segments, None), "duration_s": round(duration, 2)}


@app.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...), language: str | None = Form(default=None), prompt: str | None = Form(default=None),
    prompt_uz: str | None = Form(default=None), prompt_ru: str | None = Form(default=None),
) -> dict:
    global waiting
    if state["model"] is None:
        raise HTTPException(status_code=503, detail="model_loading")
    data = await audio.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="too_large")
    if not data:
        raise HTTPException(status_code=422, detail="empty_audio")
    lang = language.strip().lower() if language else None
    if lang in ("", "auto"):
        lang = None
    if lang is not None and lang not in LANGUAGES:
        raise HTTPException(status_code=422, detail="bad_language")
    if waiting >= CONCURRENCY + QUEUE:
        raise HTTPException(status_code=503, detail="busy")
    waiting += 1
    try:
        async with gate:
            t0 = time.perf_counter()
            try:
                prompts = {"": (prompt or "")[:600], "uz": (prompt_uz or "")[:600], "ru": (prompt_ru or "")[:600]}
                result = await asyncio.to_thread(_run, data, lang, prompts)
            except ValueError as exc:
                if str(exc) == "too_long":
                    raise HTTPException(status_code=413, detail="too_long") from exc
                raise HTTPException(status_code=422, detail="bad_audio") from exc
            except HTTPException:
                raise
            except Exception as exc:  # an undecodable / corrupt file
                log.warning("transcribe failed: %s", type(exc).__name__)
                raise HTTPException(status_code=422, detail="bad_audio") from exc
            ms = int((time.perf_counter() - t0) * 1000)
    finally:
        waiting -= 1
    log.info("transcribed bytes=%d audio_s=%.1f lang=%s ms=%d words=%d", len(data), result["duration_s"], result["language"], ms, len(result["text"].split()))
    return {**result, "ms": ms}
