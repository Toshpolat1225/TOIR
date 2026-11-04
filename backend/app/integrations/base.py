from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SourceObject:
    source: str
    external_id: str
    name: str | None
    number: str | None = None
    serial: str | None = None
    inventory: str | None = None
    model: str | None = None
    type: str | None = None


@runtime_checkable
class SourceAdapter(Protocol):
    source: str
    mirror_table: str

    async def fetch_snapshot(self) -> list[SourceObject]: ...
