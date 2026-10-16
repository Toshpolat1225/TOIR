from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Locale = Literal["uz-Latn", "uz-Cyrl", "ru"]
TranslationEntity = Literal[
    "department",
    "section",
    "work_type",
    "work_subtask",
    "nomenclature",
    "asset_type",
    "asset_status",
]


class TranslationRead(BaseModel):
    id: str
    source_name: str
    name: str
    locale: Locale
    translation_missing: bool
    translations: dict[Locale, str]
    missing_locales: list[Locale]


class TranslationWrite(BaseModel):
    name: str = Field(min_length=1, max_length=500)


class TranslationDetail(BaseModel):
    id: str
    source_name: str
    translations: dict[Locale, str]
    missing_locales: list[Locale]


class TranslationList(BaseModel):
    items: list[TranslationRead]
    total: int
    limit: int
    offset: int


class TranslatedAssetReferenceRead(BaseModel):
    code: str
    is_active: bool
    translations: dict[Locale, str]
    missing_locales: list[Locale]
    updated_at: datetime | None = None
