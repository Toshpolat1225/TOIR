from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import require_permission
from app.core.security import get_current_user
from app.models.assistant import AssistantQuery
from app.models.identity import User
from app.schemas.assistant import (
    AssistantStatus, CommandIn, CommandOut, ConfirmIn, HelpOut, TranscribeOut, UnmatchedItem, UnmatchedPage,
)
from app.services.assistant import engine

router = APIRouter(tags=["assistant"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
Admin = Annotated[User, Depends(require_permission("users.manage_users"))]
MAX_AUDIO_BYTES = 2 * 1024 * 1024
_AUDIO_TYPES = ("audio/", "video/webm", "video/mp4", "application/ogg")


@router.post("/assistant/command", response_model=CommandOut)
async def run_command(body: CommandIn, user: CurrentUser, db: DatabaseSession) -> CommandOut:
    """One typed or spoken (already transcribed) sentence: understood by rules, answered from the system's own services (read-only; a write asks for a confirmation)."""
    engine.check_rate(user.id, "command")
    return await engine.run_command(db, user, body)


@router.post("/assistant/confirm", response_model=CommandOut)
async def confirm_command(body: ConfirmIn, user: CurrentUser, db: DatabaseSession) -> CommandOut:
    """Confirm (or cancel) a pending write within a minute; used once; the action re-checks permission and section."""
    engine.check_rate(user.id, "confirm")
    return await engine.confirm_command(db, user, body)


@router.post("/assistant/transcribe", response_model=TranscribeOut)
async def transcribe(
    user: CurrentUser,
    audio: Annotated[UploadFile, File(description="webm/ogg/wav, <= 2 MB, <= 30 s")],
    language: Annotated[str | None, Form(max_length=4)] = None,
) -> TranscribeOut:
    """Speech to text on the local recogniser (the audio is never stored). Send the text to /assistant/command with source=voice."""
    from app.services.assistant import speech

    engine.check_rate(user.id, "transcribe")
    content_type = (audio.content_type or "").lower()
    if content_type and not content_type.startswith(_AUDIO_TYPES):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Audio file expected")
    data = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Audio is larger than 2 MB")
    if not data:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Empty audio")
    lang = language if language in ("uz", "ru") else None
    try:
        return await speech.transcribe(data, content_type or "audio/webm", lang, speech.DOMAIN_PROMPT)
    except speech.SpeechError as exc:
        code = {"unavailable": 503, "busy": 503, "too_long": 413, "bad_audio": 422}.get(exc.code, 502)
        raise HTTPException(status_code=code, detail=f"Speech recognition: {exc.code}") from exc


@router.get("/assistant/status", response_model=AssistantStatus)
async def read_status(user: CurrentUser) -> AssistantStatus:
    from app.services.assistant import speech

    return await speech.status()


@router.get("/assistant/help", response_model=HelpOut)
async def read_help(user: CurrentUser, db: DatabaseSession) -> HelpOut:
    """The commands this user can use (by permission), with examples in Uzbek and Russian."""
    return await engine.help_for(db, user)


@router.get("/assistant/unmatched", response_model=UnmatchedPage)
async def read_unmatched(
    user: Admin,
    db: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UnmatchedPage:
    """Sentences nobody understood, most frequent first: the list the catalogue grows from (nothing is learned automatically)."""
    base = select(
        AssistantQuery.text, func.count().label("n"), func.max(AssistantQuery.created_at).label("last_at"), func.max(AssistantQuery.best_intent).label("best")
    ).where(AssistantQuery.status == "unmatched").group_by(AssistantQuery.text)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(base.order_by(func.count().desc(), func.max(AssistantQuery.created_at).desc()).limit(limit).offset(offset))).all()
    return UnmatchedPage(items=[UnmatchedItem(text=t, count=n, last_at=last, best_intent=best) for t, n, last, best in rows], total=total)
