"""The speech-to-text client (httpx.MockTransport): success, busy, timeout, unavailable, the prompt travels, no text in the logs."""
import logging
from unittest.mock import patch

import httpx
import pytest

from app.core.config import settings
from app.services.assistant import speech

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _whisper_url():
    speech.reset_status_cache()
    with patch.object(settings, "whisper_url", "http://whisper.test"):
        yield
    speech.reset_status_cache()


def _multipart_field(request: httpx.Request, name: str) -> str | None:
    body = request.content.decode("utf-8", errors="ignore")
    marker = f'name="{name}"'
    if marker not in body:
        return None
    return body.split(marker, 1)[1].split("\r\n\r\n", 1)[1].split("\r\n--", 1)[0]


async def test_a_successful_transcription_maps_the_service_answer():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["prompt"], seen["language"] = str(request.url), _multipart_field(request, "prompt"), _multipart_field(request, "language")
        return httpx.Response(200, json={"text": " найди 37919 ", "language": "ru", "confidence": 0.91, "duration_s": 3.2, "ms": 850})

    out = await speech.transcribe(b"RIFFdata", "audio/webm", "ru", transport=httpx.MockTransport(handler))
    assert (out.text, out.language, out.confidence, out.duration_s, out.ms) == ("найди 37919", "ru", 0.91, 3.2, 850)
    assert seen["url"] == "http://whisper.test/transcribe" and seen["language"] == "ru"
    assert "naryad" in seen["prompt"] and "37919" in seen["prompt"]  # the default domain vocabulary is sent


async def test_a_custom_prompt_replaces_the_default_and_auto_language_is_not_sent():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["prompt"], seen["language"] = _multipart_field(request, "prompt"), _multipart_field(request, "language")
        return httpx.Response(200, json={"text": "ok"})

    await speech.transcribe(b"x", "audio/ogg", None, "mening lugʻatim", transport=httpx.MockTransport(handler))
    assert seen["prompt"] == "mening lugʻatim" and seen["language"] is None


@pytest.mark.parametrize(
    "status_code,detail,code",
    [(503, "busy", "busy"), (503, "model_loading", "unavailable"), (413, "too_long", "too_long"), (422, "bad_audio", "bad_audio"), (500, "x", "unavailable")],
)
async def test_service_errors_map_to_speech_error_codes(status_code, detail, code):
    transport = httpx.MockTransport(lambda r: httpx.Response(status_code, json={"detail": detail}))
    with pytest.raises(speech.SpeechError) as info:
        await speech.transcribe(b"x", "audio/webm", "uz", transport=transport)
    assert info.value.code == code


async def test_a_timeout_is_busy_and_a_dead_service_is_unavailable():
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    def dead(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(speech.SpeechError) as timeout:
        await speech.transcribe(b"x", "audio/webm", None, transport=httpx.MockTransport(slow))
    assert timeout.value.code == "busy"
    with pytest.raises(speech.SpeechError) as down:
        await speech.transcribe(b"x", "audio/webm", None, transport=httpx.MockTransport(dead))
    assert down.value.code == "unavailable"


async def test_no_url_means_unavailable_without_any_request():
    with patch.object(settings, "whisper_url", None):
        with pytest.raises(speech.SpeechError) as info:
            await speech.transcribe(b"x", "audio/webm", None)
        assert info.value.code == "unavailable"
        assert (await speech.status(force=True)).voice_available is False


async def test_status_reports_the_model_and_is_cached_for_30_seconds():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"ok": True, "model": "small", "loaded": True})

    transport = httpx.MockTransport(handler)
    first = await speech.status(transport=transport)
    assert (first.voice_available, first.voice_model, first.max_audio_s) == (True, "small", 30)
    await speech.status(transport=transport)
    assert calls == ["/health"]  # the second call came from the cache
    assert (await speech.status(transport=transport, force=True)).voice_available is True and len(calls) == 2


async def test_status_is_false_when_the_model_is_not_loaded_or_the_service_is_down():
    not_loaded = httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": True, "model": "base", "loaded": False}))
    assert (await speech.status(transport=not_loaded, force=True)).voice_available is False

    def dead(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("t", request=request)

    assert (await speech.status(transport=httpx.MockTransport(dead), force=True)).voice_available is False


async def test_the_recognised_text_is_never_logged(caplog):
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"text": "maxfiy gap 37919", "ms": 10}))
    with caplog.at_level(logging.DEBUG):
        await speech.transcribe(b"secret-audio", "audio/webm", None, transport=transport)
    assert "maxfiy gap" not in caplog.text and "secret-audio" not in caplog.text
