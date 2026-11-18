"""Client of the local speech-to-text service (compose service `whisper`). Audio and recognised text are never logged."""
from __future__ import annotations

import logging
import time

import httpx

from app.core.config import settings
from app.schemas.assistant import AssistantStatus, TranscribeOut

logger = logging.getLogger(__name__)

TIMEOUT_S = 60.0
STATUS_TIMEOUT_S = 2.0
STATUS_TTL_S = 30.0
MAX_AUDIO_S = 30

# Vocabulary hint (Whisper's initial_prompt): domain words and the way numbers are spoken. Kept short: the service cuts it at 600 characters.
DOMAIN_PROMPT = (
    "Buyruqlar: naryad, naryadlar, sostav, lokomotiv, vagon, teplovoz, elektrovoz, Wialon, GTK, vesovoy, tarozi, texnik xizmat, ТО, probeg, "
    "xarita, qayerda, nechta, bugun, kecha. Команды: наряд, состав, локомотив, вагон, Виалон, ГТК, весовая, ТО, пробег, карта, где, сколько, "
    "сегодня, вчера. Номера: тридцать семь девятьсот девятнадцать, 37919, o'ttiz yetti to'qqiz yuz o'n to'qqiz."
)

PROMPT_UZ = (
    "Xaritani och. Naryadlar ro'yxati. Ochiq naryadlar. 37919 qayerda? 37919 bugun necha kilometr yurdi? 37919 probegi. Sostav 439. Vagonlar. "
    "Muddati o'tgan texnik xizmat. O'lik GTK trekerlar. Wialon oxirgi yangilanish. Bugun nechta sostav tortildi? Vesovoy. Nima qila olasan? Yordam. Ha. Yo'q."
)
PROMPT_RU = (
    "Открой карту. Открытые наряды. Где 37919? Сколько проехал 37919 сегодня? Пробег 37919. Состав 439. Вагоны. "
    "Просроченные ТО. Мёртвые трекеры ГТК. Когда обновился Виалон? Сколько тонн перевезли сегодня? Весовая. Что ты умеешь? Помощь. Да. Нет."
)


class SpeechError(Exception):
    """`code`: unavailable | too_long | busy | bad_audio."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


_status_cache: tuple[float, AssistantStatus] | None = None


def _base_url() -> str | None:
    return settings.whisper_url


async def transcribe(
    audio: bytes,
    content_type: str,
    language: str | None = None,
    prompt: str | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> TranscribeOut:
    """Send one recording to the recogniser. `language`: uz | ru | None (auto). `prompt`: vocabulary hint (default `DOMAIN_PROMPT`)."""
    base = _base_url()
    if not base:
        raise SpeechError("unavailable")
    data = {"prompt": prompt if prompt is not None else DOMAIN_PROMPT}
    if prompt is None:  # a per-language prompt: sentences in the style of real commands steer a small model far better than a word list
        data["prompt_uz"] = PROMPT_UZ
        data["prompt_ru"] = PROMPT_RU
    if language in ("uz", "ru"):
        data["language"] = language
    files = {"audio": ("speech", audio, content_type or "application/octet-stream")}
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, transport=transport) as client:
            response = await client.post(f"{base}/transcribe", data=data, files=files)
    except httpx.TimeoutException as exc:
        raise SpeechError("busy") from exc  # the recogniser is overloaded or stuck: the caller may retry
    except httpx.HTTPError as exc:
        raise SpeechError("unavailable") from exc
    if response.status_code == 503:
        detail = _detail(response)
        raise SpeechError("busy" if detail == "busy" else "unavailable")
    if response.status_code == 413:
        raise SpeechError("too_long")
    if response.status_code in (400, 415, 422):
        raise SpeechError("bad_audio")
    if response.status_code >= 400:
        raise SpeechError("unavailable")
    try:
        body = response.json()
    except ValueError as exc:
        raise SpeechError("unavailable") from exc
    ms = int(body.get("ms") or (time.perf_counter() - started) * 1000)
    logger.info("transcribed bytes=%d ms=%d", len(audio), ms)  # sizes and timings only: never the audio or the text
    return TranscribeOut(
        text=str(body.get("text") or "").strip(), language=body.get("language"), confidence=body.get("confidence"),
        duration_s=body.get("duration_s"), ms=ms,
    )


def _detail(response: httpx.Response) -> str | None:
    try:
        return str(response.json().get("detail"))
    except (ValueError, AttributeError):
        return None


async def status(*, transport: httpx.AsyncBaseTransport | None = None, force: bool = False) -> AssistantStatus:
    """Is the recogniser up? Cached for 30 seconds; any failure means `voice_available = False` (the text assistant is unaffected)."""
    global _status_cache
    now = time.monotonic()
    if not force and _status_cache is not None and now - _status_cache[0] < STATUS_TTL_S:
        return _status_cache[1]
    result = AssistantStatus(voice_available=False, voice_model=None, max_audio_s=MAX_AUDIO_S)
    base = _base_url()
    if base:
        try:
            async with httpx.AsyncClient(timeout=STATUS_TIMEOUT_S, transport=transport) as client:
                response = await client.get(f"{base}/health")
            body = response.json() if response.status_code == 200 else {}
            if body.get("ok") and body.get("loaded"):
                result = AssistantStatus(voice_available=True, voice_model=body.get("model") or settings.whisper_model, max_audio_s=MAX_AUDIO_S)
        except (httpx.HTTPError, ValueError):
            pass
    _status_cache = (now, result)
    return result


def reset_status_cache() -> None:
    global _status_cache
    _status_cache = None
