FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./alembic.ini
COPY backend/entrypoint.sh ./entrypoint.sh

RUN chmod 0555 ./entrypoint.sh \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

USER appuser

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
