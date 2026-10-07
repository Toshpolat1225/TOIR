import json
import hmac
from typing import Annotated, Any
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.services import assets as service

router = APIRouter(prefix="/wialon", tags=["wialon"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
MAX_INPUT_BYTES = 64 * 1024
UNIT_KEYS = ("i", "unitId", "unit_id", "id", "uid", "unit")
NAME_KEYS = ("nm", "name", "unit_name", "na")
MILEAGE_KEYS = (
    "mileage",
    "odo",
    "odometer",
    "km",
    "total_odometer",
    "total_km",
    "run",
)
SPEED_KEYS = ("speed", "spd", "vel")


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid Wialon ingest credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_ingest_token(request: Request) -> None:
    configured = settings.wialon_ingest_token
    expected = configured.get_secret_value() if configured is not None else ""
    candidates: list[str] = []

    authorization = request.headers.get("authorization", "")
    scheme, separator, value = authorization.partition(" ")
    if separator and scheme.lower() == "bearer" and value.strip():
        candidates.append(value.strip())
    header_token = request.headers.get("x-ingest-token")
    if header_token:
        candidates.append(header_token.strip())
    query_tokens = getattr(request.state, "wialon_query_tokens", ())
    candidates.extend(token for token in query_tokens if token)

    matched = False
    for candidate in candidates:
        matched = hmac.compare_digest(
            candidate.encode("utf-8"), expected.encode("utf-8")
        ) or matched
    if not expected or not matched:
        raise _unauthorized()


def _first_value(payload: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is not None and value != "":
            return value
    return None


def _query_payload(request: Request) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    pairs = getattr(request.state, "wialon_query_pairs", ())
    for key, value in pairs:
        if key.lower() != "token":
            payload[key] = value
    return payload


async def _read_limited_body(request: Request, query_size: int) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if query_size + int(content_length) > MAX_INPUT_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Wialon request exceeds 64 KB",
                )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Content-Length",
            ) from exc

    chunks: list[bytes] = []
    total = query_size
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_INPUT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Wialon request exceeds 64 KB",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _decode_form(raw: bytes) -> dict[str, Any]:
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Wialon payload must be UTF-8",
        ) from exc
    values = parse_qs(decoded, keep_blank_values=True)
    return {key: value[-1] for key, value in values.items()}


def _decode_body(raw: bytes, content_type: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Wialon payload must be UTF-8",
        ) from exc
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type == "application/x-www-form-urlencoded":
        return _decode_form(raw)
    if media_type == "application/json" or media_type.endswith("+json"):
        try:
            payload = json.loads(decoded)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid Wialon JSON payload",
            ) from exc
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Wialon payload must be an object",
            )
        return payload
    if media_type == "text/plain":
        try:
            payload = json.loads(decoded)
        except json.JSONDecodeError:
            return _decode_form(raw)
        if isinstance(payload, dict):
            return payload
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Wialon payload must be an object",
        )
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Use JSON, form-urlencoded, or text/plain Wialon payload",
    )


async def _handle_input(request: Request, db: AsyncSession) -> dict[str, Any]:
    if getattr(request.state, "wialon_query_size", 0) > MAX_INPUT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Wialon request exceeds 64 KB",
        )
    payload = _query_payload(request)
    if request.method == "POST":
        raw = await _read_limited_body(
            request, getattr(request.state, "wialon_query_size", 0)
        )
        payload.update(_decode_body(raw, request.headers.get("content-type", "")))

    unit_id = _first_value(payload, UNIT_KEYS)
    unit_name = _first_value(payload, NAME_KEYS)
    if unit_id is None and unit_name is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A Wialon unit ID or name is required",
        )

    mileage = service.parse_wialon_decimal(
        _first_value(payload, MILEAGE_KEYS), "mileage"
    )
    speed = service.parse_wialon_decimal(_first_value(payload, SPEED_KEYS), "speed")
    return await service.receive_wialon_update(
        db,
        unit_id=str(unit_id).strip() if unit_id is not None else None,
        unit_name=str(unit_name).strip() if unit_name is not None else None,
        mileage=mileage,
        speed=speed,
    )


@router.post("/input", dependencies=[Depends(require_ingest_token)])
async def post_wialon_input(request: Request, db: DatabaseSession):
    return await _handle_input(request, db)


@router.get("/input", dependencies=[Depends(require_ingest_token)])
async def get_wialon_input(request: Request, db: DatabaseSession):
    return await _handle_input(request, db)
