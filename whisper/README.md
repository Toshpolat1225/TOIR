# whisper: local speech-to-text for the TOIR command centre

Free, local, CPU only (faster-whisper + int8). The model is downloaded **when the image is built** and baked into it: the server needs no
internet at run time. The service is internal (port 9000 is not published); only the TOIR backend calls it. The assistant works without it
(text mode); the backend reports `voice_available = false` and the microphone button is hidden.

## Build and run

```
docker compose build whisper                  # WHISPER_MODEL=small by default (base: WHISPER_MODEL=base); needs internet once
docker compose up -d --no-deps whisper
docker compose exec whisper python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:9000/health').read())"
```

Choose the model with the env var `WHISPER_MODEL` (tiny | base | small) **before building** (it is baked in): `WHISPER_MODEL=small docker compose build whisper`.
Limits: `WHISPER_MEM` (default 1536m), `WHISPER_CPUS` (default 2.0).

## Models (CPU, int8) - measured on a 12-core i7-12700, container limited to 2 CPUs / 1.5 GB

| Model | Resident RAM | Latency per 3-5 s clip (warm) | Russian command accuracy (10 TTS phrases) |
|---|---|---|---|
| tiny  | not measured (~0.3 GB expected) | not measured | not measured |
| base  | ~230 MB | ~0.6 s (`language=ru`), ~1.0 s (`auto`: language detection costs ~0.4 s) | WER 0.075, 8/10 phrases exact, numbers 5/6 |
| small | ~930 MB | ~1.6 s (`ru`), ~2.9 s (`auto`) | WER 0.092, 8/10 phrases exact, numbers 6/6 |

A server CPU is slower than this PC: expect 2-4x the latencies. Always send `language` (uz or ru) when known: `auto` is slower.
The image is ~1.6 GB (python + onnxruntime + the model). Uzbek was NOT measured (no Uzbek voice/recordings): see `backend/scripts/e2e_live/speech_measure.py`.

## API

- `GET /health` -> `{ok, model, loaded}`
- `POST /transcribe` multipart: `audio` (webm/ogg/opus/wav/mp4; <= 2 MB, <= 30 s), `language` (`uz` | `ru` | `auto`), `prompt` (vocabulary hint, <= 600 chars)
  -> `{text, language, confidence, duration_s, ms}`.
  `confidence` = mean over segments of `exp(avg_logprob)` (the average token probability, 0..1); the language probability if no segment.
  Errors: 413 `too_large` / `too_long`, 422 `empty_audio` / `bad_audio` / `bad_language`, 503 `busy` (queue full: 1 running + 2 waiting) / `model_loading`.
- No audio is written to disk; logs contain sizes, durations and timings but never the recognised text.

## Server without internet

Bake the model on a PC that has internet and ship the image:

```
WHISPER_MODEL=base docker compose build whisper
docker save toir-whisper:latest | gzip > toir-whisper.tar.gz          # copy the file to the server
gunzip -c toir-whisper.tar.gz | docker load                           # on the server
docker compose up -d --no-deps whisper                                # (without --build; the image is already there)
```

(The image name is `<project>-whisper`; check with `docker images`.)
