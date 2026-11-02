"""Store Wialon units separately from fixed assets."""

from alembic import op
import sqlalchemy as sa

revision = "0012_wialon_units"
down_revision = "0011_wialon_counter_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wialon_units",
        sa.Column("unit_id", sa.String(length=100), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("cnm", sa.Numeric(16, 2), nullable=True),
        sa.Column("cneh", sa.Numeric(14, 3), nullable=True),
        sa.Column("calc_flags", sa.Integer(), nullable=True),
        sa.Column("speed", sa.Numeric(6, 2), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "suspect_absolute",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_wialon_units_name", "wialon_units", ["name"])
    op.create_index(
        "ix_wialon_units_last_message_at", "wialon_units", ["last_message_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_wialon_units_last_message_at", table_name="wialon_units")
    op.drop_index("ix_wialon_units_name", table_name="wialon_units")
    op.drop_table("wialon_units")
