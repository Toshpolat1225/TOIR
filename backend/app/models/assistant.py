"""Command centre persistence: a log of questions (text only: audio is never stored) and pending confirmations of write actions."""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text as sql_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AssistantQuery(Base):
    __tablename__ = "assistant_queries"
    __table_args__ = (
        CheckConstraint("source IN ('text','voice')", name="ck_assistant_queries_source"),
        Index("ix_assistant_queries_created_at", "created_at"),
        Index("ix_assistant_queries_status", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    text: Mapped[str] = mapped_column(Text, nullable=False)  # the canonical sentence (what the parser saw)
    locale: Mapped[str] = mapped_column(Text, nullable=False, server_default=sql_text("'uz'"))
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default=sql_text("'text'"))
    intent: Mapped[str | None] = mapped_column(Text)
    best_intent: Mapped[str | None] = mapped_column(Text)  # the closest intent when nothing matched
    status: Mapped[str] = mapped_column(Text, nullable=False)  # ok | unmatched | denied | needs_confirm | needs_clarification | error | confirmed | cancelled
    ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default=sql_text("0"))
    stt_confidence: Mapped[float | None] = mapped_column()
    entities: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AssistantPending(Base):
    """A write the user has to confirm within a minute; used once."""

    __tablename__ = "assistant_pending"
    __table_args__ = (Index("ix_assistant_pending_user", "user_id", "expires_at"),)

    token: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str] = mapped_column(Text, nullable=False, server_default=sql_text("'uz'"))
    risk: Mapped[str] = mapped_column(Text, nullable=False, server_default=sql_text("'low'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(Text)  # confirmed | cancelled | expired | failed
