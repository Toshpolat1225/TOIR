"""Internal types of the command centre. Handlers receive `Ctx` + `Slots` and return `Result`; they never touch HTTP."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User
from app.schemas.assistant import AssistantContext, Card, EntityRef

Period = Literal["today", "yesterday", "week", "month"]
LOCOMOTIVE_TYPES = ("locomotive", "diesel", "special_self_propelled")


@dataclass
class AssetRef:
    id: UUID
    inv_number: str
    name: str
    asset_type: str
    section_id: UUID | None = None
    section_name: str | None = None
    model_name: str | None = None
    gtk_id: int | None = None  # GTK unit/carriage id from the active link (None when not linked)

    @property
    def is_locomotive(self) -> bool:
        return self.asset_type in LOCOMOTIVE_TYPES

    def entity(self) -> EntityRef:
        return EntityRef(kind="asset", id=str(self.id), label=self.inv_number, asset_type=self.asset_type)


@dataclass
class Slots:
    """What the parser found in the sentence. Handlers read only the slots their intent declares."""

    asset: AssetRef | None = None
    assets: list[AssetRef] = field(default_factory=list)  # ambiguous matches (asset is None then)
    train_no: str | None = None  # the GTK train number as spoken/typed
    train_gtk_id: int | None = None
    work_order: str | None = None  # the number the user said (matched by the handler)
    work_order_id: UUID | None = None
    section_id: UUID | None = None
    section_name: str | None = None
    period: Period = "today"
    page: str | None = None  # a page key from `catalog.PAGES`
    status: str | None = None  # work order status asked for / to set: pending | in_progress | completed | cancelled
    text: str | None = None  # free text after "izoh" / "комментарий" / "tavsif"
    number: int | None = None  # a bare number (limit, month)
    raw_numbers: list[str] = field(default_factory=list)
    asset_from_context: bool = False  # the asset came from the page / the last answer, not from the sentence
    pronoun: bool = False  # the sentence points back with a pronoun (bu, uni, этот, его)


@dataclass
class Ctx:
    db: AsyncSession
    user: User
    locale: Literal["uz", "ru"]
    context: AssistantContext | None
    now: datetime

    @property
    def master_section_id(self) -> UUID | None:
        return self.user.section_id if self.user.role == "master" else None


@dataclass
class PendingAction:
    """A write the user must confirm. `kind` selects the registered action executor, `payload` is JSON-safe."""

    kind: str  # wo.create | wo.set_status | wo.comment
    payload: dict[str, Any]
    summary: str  # one line, in the user's language
    risk: Literal["low", "medium"] = "low"


@dataclass
class Result:
    cards: list[Card] = field(default_factory=list)
    speak: str | None = None
    navigate: str | None = None
    entities: list[EntityRef] = field(default_factory=list)
    pending: PendingAction | None = None
    status: Literal["ok", "needs_clarification", "denied", "error"] = "ok"


Handler = Callable[[Ctx, Slots], Awaitable[Result]]
ActionExecutor = Callable[[Ctx, dict[str, Any]], Awaitable[Result]]
