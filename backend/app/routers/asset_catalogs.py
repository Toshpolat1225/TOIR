from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.localization import Locale, get_locale
from app.core.security import get_current_user, require_role
from app.models.identity import User
from app.schemas.asset_catalogs import AssetCatalogList, AssetCatalogUpdate, AssetCatalogWrite, CatalogKind
from app.services import asset_catalogs as service

router = APIRouter(prefix="/fixed-asset-catalogs", tags=["fixed asset catalogs"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
AuthenticatedUser = Annotated[User, Depends(get_current_user)]
CatalogAdmin = Annotated[User, Depends(require_role("admin"))]


@router.get("/{kind}", response_model=AssetCatalogList)
async def list_items(kind: CatalogKind, _: AuthenticatedUser, db: DatabaseSession,
                     locale: Annotated[Locale, Depends(get_locale)],
                     q: str | None = Query(default=None, max_length=200),
                     is_active: bool | None = None,
                     limit: int = Query(default=100, ge=1, le=1000),
                     offset: int = Query(default=0, ge=0)):
    return await service.list_items(db, kind=kind, locale=locale, q=q,
                                    is_active=is_active, limit=limit, offset=offset)


@router.post("/{kind}", status_code=status.HTTP_201_CREATED)
async def create(kind: CatalogKind, payload: AssetCatalogWrite, _: CatalogAdmin, db: DatabaseSession):
    return await service.create(db, kind=kind, payload=payload)


@router.put("/{kind}/{code}")
async def update(kind: CatalogKind, code: str, payload: AssetCatalogUpdate, _: CatalogAdmin, db: DatabaseSession):
    return await service.update(db, kind=kind, code=code, payload=payload)


@router.delete("/{kind}/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(kind: CatalogKind, code: str, _: CatalogAdmin, db: DatabaseSession):
    await service.delete(db, kind=kind, code=code)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
