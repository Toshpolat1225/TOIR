from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_current_user, unauthorized_exception
from app.models.identity import User
from app.schemas.auth import AccessTokenResponse, LoginRequest
from app.schemas.users import UserRead
from app.services.auth import authenticate, revoke_refresh_token, rotate_refresh_token

router = APIRouter(prefix="/auth", tags=["authentication"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
REFRESH_COOKIE_NAME = "toir_refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


@router.post("/login", response_model=AccessTokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DatabaseSession,
) -> AccessTokenResponse:
    client_ip = request.client.host if request.client is not None else "unknown"
    tokens = await authenticate(db, payload, client_ip)
    _set_refresh_cookie(response, request, tokens.refresh_token)
    return AccessTokenResponse(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
    )


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: DatabaseSession,
) -> AccessTokenResponse | JSONResponse:
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token:
        rejected = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": unauthorized_exception().detail},
            headers={"WWW-Authenticate": "Bearer"},
        )
        _clear_refresh_cookie(rejected, request)
        return rejected

    try:
        tokens = await rotate_refresh_token(db, refresh_token)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            rejected = JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers,
            )
            _clear_refresh_cookie(rejected, request)
            return rejected
        raise

    _set_refresh_cookie(response, request, tokens.refresh_token)
    return AccessTokenResponse(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, db: DatabaseSession) -> Response:
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if refresh_token:
        await revoke_refresh_token(db, refresh_token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_refresh_cookie(response, request)
    return response


@router.get("/me", response_model=UserRead)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    return current_user
