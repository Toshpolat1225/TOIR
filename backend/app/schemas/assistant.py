"""The voice/text command centre: request and response shapes (the contract between the frontend, the parser and the handlers)."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Tone = Literal["ok", "warn", "bad", "info", "muted"]
CardKind = Literal["asset", "wagon", "train", "list", "metric", "text", "table", "confirm", "help", "error"]
Status = Literal["ok", "unmatched", "denied", "needs_confirm", "needs_clarification", "error"]


class EntityRef(BaseModel):
    kind: Literal["asset", "train", "work_order", "section"]
    id: str  # asset uuid / GTK train id / work order uuid / section uuid
    label: str
    asset_type: str | None = None  # asset only: locomotive | diesel | wagon | tank_car | platform | ...


class DialogState(BaseModel):
    """An unfinished command waiting for its missing piece: the next short answer is appended to `base` and parsed again (the server keeps no state)."""

    intent: str = Field(max_length=60)
    base: str = Field(max_length=400)


class AssistantContext(BaseModel):
    """Where the user is and what was talked about last: "bu lokomotiv", "uni xaritada ko'rsat"."""

    page: str | None = Field(default=None, max_length=200)  # location.pathname
    asset_id: UUID | None = None
    train_gtk_id: int | None = None
    last_entity: EntityRef | None = None
    dialog: DialogState | None = None


class CommandIn(BaseModel):
    text: str = Field(min_length=1, max_length=400)
    locale: Literal["uz", "ru", "auto"] = "auto"
    source: Literal["text", "voice"] = "text"
    stt_confidence: float | None = Field(default=None, ge=0, le=1)  # from the speech recogniser, when source = voice
    context: AssistantContext | None = None


class CardRow(BaseModel):
    label: str
    value: str
    tone: Tone | None = None


class CardItem(BaseModel):
    label: str
    sub: str | None = None
    value: str | None = None
    href: str | None = None  # an in-app path
    tone: Tone | None = None
    entity: EntityRef | None = None  # a click can continue the conversation ("bu")


class Card(BaseModel):
    kind: CardKind
    title: str
    subtitle: str | None = None
    tone: Tone | None = None
    rows: list[CardRow] = Field(default_factory=list)  # key/value lines (asset, wagon, train, metric, text)
    items: list[CardItem] = Field(default_factory=list)  # kind = list / help
    columns: list[str] = Field(default_factory=list)  # kind = table: the header ...
    table: list[list[str]] = Field(default_factory=list)  # ... and the rows
    href: str | None = None  # the main "open" link
    badge: str | None = None


class Suggestion(BaseModel):
    text: str  # a phrase the user can say or tap
    intent: str | None = None


class ConfirmOut(BaseModel):
    token: str
    expires_at: datetime
    summary: str  # "Naryad ochish: 37919, ТО-2, uchastka ..."
    risk: Literal["low", "medium"] = "low"


class CommandOut(BaseModel):
    ok: bool
    status: Status
    intent: str | None = None
    heard: str  # the normalised text the parser saw: the user can check "Siz aytdingiz"
    speak: str | None = None  # a short sentence for the text-to-speech (the frontend decides whether it can voice it)
    speak_lang: Literal["uz", "ru"] = "ru"
    cards: list[Card] = Field(default_factory=list)
    navigate: str | None = None  # an in-app path to open
    confirm: ConfirmOut | None = None
    suggestions: list[Suggestion] = Field(default_factory=list)
    entities: list[EntityRef] = Field(default_factory=list)  # what was resolved: becomes `context.last_entity`
    ms: int = 0
    query_id: int | None = None
    dialog: DialogState | None = None  # set when the command still lacks something: the client sends it back with the next answer


class ConfirmIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    approve: bool = True
    context: AssistantContext | None = None


class TranscribeOut(BaseModel):
    text: str
    language: str | None = None
    confidence: float | None = None
    duration_s: float | None = None
    ms: int = 0


class AssistantStatus(BaseModel):
    voice_available: bool  # the speech-to-text service answers
    voice_model: str | None = None
    max_audio_s: int = 30
    write_actions: bool = True  # commands may create work orders etc. (always with a confirmation)


class HelpGroup(BaseModel):
    module: str
    title: str
    examples: list[str]


class HelpOut(BaseModel):
    groups: list[HelpGroup]


class UnmatchedItem(BaseModel):
    text: str
    count: int
    last_at: datetime
    best_intent: str | None = None


class UnmatchedPage(BaseModel):
    items: list[UnmatchedItem]
    total: int
