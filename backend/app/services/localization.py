from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.repositories import localization as repository
from app.schemas.localization import Locale

SUPPORTED_LOCALES: tuple[Locale, ...] = ("uz-Latn", "uz-Cyrl", "ru")


async def list_localized_entities(
    db: AsyncSession,
    *,
    entity_type: str,
    locale: Locale,
    q: str | None,
    limit: int,
    offset: int,
    master_section_id: UUID | None,
) -> dict:
    items, total = await repository.list_entities(
        db,
        entity_type=entity_type,
        locale=locale,
        q=q,
        limit=limit,
        offset=offset,
        master_section_id=master_section_id,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


async def get_translation_detail(
    db: AsyncSession, *, entity_type: str, entity_id: str,
    master_section_id: UUID | None = None,
) -> dict:
    entity = await repository.get_entity(
        db, entity_type=entity_type, entity_id=entity_id,
        master_section_id=master_section_id,
    )
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Translation target not found")
    key, source_name, translations = entity
    return {
        "id": key,
        "source_name": source_name,
        "translations": translations,
        "missing_locales": [locale for locale in SUPPORTED_LOCALES if locale not in translations],
    }


async def set_translation(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
    locale: Locale,
    name: str,
) -> dict:
    normalized = name.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail="Translation must not be empty")
    if await repository.get_entity(db, entity_type=entity_type, entity_id=entity_id) is None:
        raise HTTPException(status_code=404, detail="Translation target not found")
    row = await repository.get_translation_row(
        db, entity_type=entity_type, entity_id=entity_id, locale=locale
    )
    if row is None:
        await repository.add_translation(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            locale=locale,
            name=normalized,
        )
    else:
        row.name = normalized
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail="Translation could not be saved") from exc
    return await get_translation_detail(db, entity_type=entity_type, entity_id=entity_id)


async def remove_translation(
    db: AsyncSession, *, entity_type: str, entity_id: str, locale: Locale
) -> None:
    row = await repository.get_translation_row(
        db, entity_type=entity_type, entity_id=entity_id, locale=locale
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Translation not found")
    await db.delete(row)
    await db.commit()
