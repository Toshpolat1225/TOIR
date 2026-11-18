# Local speech-to-text for the TOIR command centre (CPU only, free). The model is baked into the image at BUILD time,
# so the server never needs internet at run time. See README.md.
FROM python:3.12-slim

ARG WHISPER_MODEL=small
ARG WHISPER_COMPUTE=int8

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WHISPER_MODEL=${WHISPER_MODEL} \
    WHISPER_COMPUTE=${WHISPER_COMPUTE} \
    WHISPER_DEVICE=cpu \
    HF_HOME=/models \
    HF_HUB_DISABLE_TELEMETRY=1 \
    OMP_NUM_THREADS=2

WORKDIR /srv
RUN pip install faster-whisper==1.1.1 fastapi==0.115.6 "uvicorn[standard]==0.34.0" python-multipart==0.0.20
# faster-whisper 1.1.1 needs the 0.x huggingface_hub (2.x dropped `requests`); a separate layer keeps the big download above cached
RUN pip install --only-binary=:all: "huggingface_hub>=0.27,<1.0" requests "av>=12,<15"  # av 19 removed an argument faster-whisper 1.1.1 passes; wheels only (no compiler here)

# download the model into the image (needs internet only here)
RUN python -c "import os; from faster_whisper import WhisperModel; WhisperModel(os.environ['WHISPER_MODEL'], device='cpu', compute_type=os.environ['WHISPER_COMPUTE'], download_root='/models')"
ENV HF_HUB_OFFLINE=1

COPY app.py /srv/app.py
RUN useradd --system --uid 10001 --home /nonexistent whisper && chown -R whisper /models
USER whisper

EXPOSE 9000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request,json,sys; d=json.load(urllib.request.urlopen('http://127.0.0.1:9000/health', timeout=4)); sys.exit(0 if d.get('loaded') else 1)"
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000", "--workers", "1", "--no-access-log"]
