"""Add Wialon counter state and rejected-reading audit tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_wialon_counter_state"
down_revision = "0010_merge_section_hierarchy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wialon_counter_state",
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fixed_assets.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("baseline_cnm", sa.Numeric(16, 2), nullable=True),
        sa.Column("last_cnm", sa.Numeric(16, 2), nullable=True),
        sa.Column("last_cnm_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("baseline_cneh", sa.Numeric(14, 3), nullable=True),
        sa.Column("last_cneh", sa.Numeric(14, 3), nullable=True),
        sa.Column("last_cneh_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("engine_hours", sa.Numeric(12, 3), nullable=True),
        sa.Column(
            "suspect_absolute",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("last_status", sa.Text(), nullable=True),
        sa.Column("last_reason", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_table(
        "wialon_rejected_readings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fixed_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("counter", sa.Text(), nullable=False),
        sa.Column("value", sa.Numeric(18, 3), nullable=True),
        sa.Column("previous_value", sa.Numeric(18, 3), nullable=True),
        sa.Column("reading_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "counter IN ('mileage','engine_hours')",
            name="wialon_rejected_counter_check",
        ),
    )
    op.create_index(
        "ix_wialon_rejected_asset_time",
        "wialon_rejected_readings",
        ["asset_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_wialon_rejected_asset_time",
        table_name="wialon_rejected_readings",
    )
    op.drop_table("wialon_rejected_readings")
    op.drop_table("wialon_counter_state")
