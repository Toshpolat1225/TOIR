from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.localization import Locale, get_locale
from app.core.permissions import require_permission
from app.models.identity import User
from app.schemas.localization import (
    Locale as LocaleSchema,
    TranslationDetail,
    TranslationEntity,
    TranslationList,
    TranslationWrite,
)
from app.services import localization as service

router = APIRouter(prefix="/translations", tags=["localization"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
AuthenticatedUser = Annotated[User, Depends(require_permission("translations.view"))]
TranslationAdmin = Annotated[User, Depends(require_permission("translations.manage_reference_data"))]


@router.get("/{entity_type}", response_model=TranslationList)
async def get_localized_entities(
    entity_type: TranslationEntity,
    current_user: AuthenticatedUser,
    db: DatabaseSession,
    locale: Annotated[Locale, Depends(get_locale)],
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> TranslationList:
    return await service.list_localized_entities(
        db,
        entity_type=entity_type,
        locale=locale,
        q=q,
        limit=limit,
        offset=offset,
        master_section_id=(
            current_user.section_id if current_user.role == "master" else None
        ),
    )


@router.get("/{entity_type}/{entity_id}", response_model=TranslationDetail)
async def get_translation(
    entity_type: TranslationEntity,
    entity_id: str,
    current_user: AuthenticatedUser,
    db: DatabaseSession,
) -> TranslationDetail:
    return await service.get_translation_detail(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        master_section_id=(current_user.section_id if current_user.role == "master" else None),
    )


@router.put("/{entity_type}/{entity_id}/{locale}", response_model=TranslationDetail)
async def put_translation(
    entity_type: TranslationEntity,
    entity_id: str,
    locale: LocaleSchema,
    payload: TranslationWrite,
    _: TranslationAdmin,
    db: DatabaseSession,
) -> TranslationDetail:
    return await service.set_translation(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        locale=locale,
        name=payload.name,
    )


@router.delete(
    "/{entity_type}/{entity_id}/{locale}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_translation(
    entity_type: TranslationEntity,
    entity_id: str,
    locale: LocaleSchema,
    _: TranslationAdmin,
    db: DatabaseSession,
) -> Response:
    await service.remove_translation(
        db, entity_type=entity_type, entity_id=entity_id, locale=locale
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
