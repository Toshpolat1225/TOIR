from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class AssetMatchSuggestion(BaseModel):
    asset_id: UUID
    name: str
    inv_number: str
    asset_type: str
    signals: list[str]


class UnmatchedSourceObjectRead(BaseModel):
    source: Literal["gtk", "wialon"]
    external_id: str
    name: str | None
    number: str | None
    serial: str | None
    inventory: str | None
    model: str | None
    type: str | None
    level: Literal["high", "ambiguous", "none"]
    candidate_count: int
    suggestion: AssetMatchSuggestion | None
    candidates: list[AssetMatchSuggestion]
    signals: list[str]
