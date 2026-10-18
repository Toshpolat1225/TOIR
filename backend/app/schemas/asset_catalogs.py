from typing import Literal

from pydantic import BaseModel, Field, field_validator

Locale = Literal["uz-Latn", "uz-Cyrl", "ru"]
CatalogKind = Literal["types", "statuses"]
AssetBehavior = Literal["operational", "maintenance", "repair", "out_of_service"]
CatalogColor = Literal["blue", "green", "amber", "orange", "red", "gray", "purple"]


class AssetCatalogWrite(BaseModel):
    code: str = Field(min_length=2, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    names: dict[Locale, str]
    is_active: bool = True
    behavior: AssetBehavior | None = None
    color: CatalogColor = "blue"

    @field_validator("names")
    @classmethod
    def require_all_locales(cls, value: dict[str, str]) -> dict[str, str]:
        locales = {"uz-Latn", "uz-Cyrl", "ru"}
        if set(value) != locales or any(not name.strip() for name in value.values()):
            raise ValueError("All three non-empty translations are required")
        return {locale: name.strip() for locale, name in value.items()}


class AssetCatalogUpdate(BaseModel):
    names: dict[Locale, str]
    is_active: bool
    behavior: AssetBehavior | None = None
    color: CatalogColor

    @field_validator("names")
    @classmethod
    def require_all_locales(cls, value: dict[str, str]) -> dict[str, str]:
        return AssetCatalogWrite.require_all_locales(value)


class AssetCatalogItem(BaseModel):
    code: str
    name: str
    names: dict[str, str]
    is_active: bool
    usage_count: int
    behavior: str | None = None
    color: str


class AssetCatalogList(BaseModel):
    items: list[AssetCatalogItem]
    total: int
    limit: int
    offset: int
