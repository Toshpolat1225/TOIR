"""Command centre (voice/text assistant): question log and pending confirmations of write actions.

Additive only: two new tables. Audio is never stored.

Revision ID: 0040_assistant
Revises: 0039_gps_odometer_heartbeat
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0040_assistant"
down_revision = "0039_gps_odometer_heartbeat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_queries",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("locale", sa.Text, nullable=False, server_default=sa.text("'uz'")),
        sa.Column("source", sa.Text, nullable=False, server_default=sa.text("'text'")),
        sa.Column("intent", sa.Text),
        sa.Column("best_intent", sa.Text),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("ms", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("stt_confidence", sa.Float),
        sa.Column("entities", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("source IN ('text','voice')", name="ck_assistant_queries_source"),
    )
    op.create_index("ix_assistant_queries_created_at", "assistant_queries", ["created_at"])
    op.create_index("ix_assistant_queries_status", "assistant_queries", ["status", "created_at"])
    op.create_table(
        "assistant_pending",
        sa.Column("token", sa.Text, primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("locale", sa.Text, nullable=False, server_default=sa.text("'uz'")),
        sa.Column("risk", sa.Text, nullable=False, server_default=sa.text("'low'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("outcome", sa.Text),
    )
    op.create_index("ix_assistant_pending_user", "assistant_pending", ["user_id", "expires_at"])


def downgrade() -> None:
    op.drop_table("assistant_pending")
    op.drop_table("assistant_queries")
