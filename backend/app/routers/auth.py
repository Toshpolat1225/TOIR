from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.identity import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
)
from app.schemas.users import UserRead
from app.services.auth import authenticate, revoke_refresh_token, rotate_refresh_token

router = APIRouter(prefix="/auth", tags=["authentication"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, request: Request, db: DatabaseSession
) -> TokenResponse:
    client_ip = request.client.host if request.client is not None else "unknown"
    return await authenticate(db, payload, client_ip)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest, db: DatabaseSession
) -> TokenResponse:
    return await rotate_refresh_token(db, payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: LogoutRequest, db: DatabaseSession) -> Response:
    await revoke_refresh_token(db, payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserRead)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    return current_user
