"""Position history of assets: the track behind the map («where was it, and when»).

Additive only: one new table. Filled by the Wialon / GTK syncs (movement-thinned) and by `wialon-track-backfill`.

Revision ID: 0036_position_history
Revises: 0035_scale_car_net
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0036_position_history"
down_revision = "0035_scale_car_net"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_position_history",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lat", sa.Numeric(10, 7), nullable=False),
        sa.Column("lon", sa.Numeric(10, 7), nullable=False),
        sa.Column("speed", sa.Numeric(6, 2)),
        sa.Column("source", sa.Text, nullable=False, server_default=sa.text("'wialon'")),
        sa.UniqueConstraint("asset_id", "at", "source", name="uq_asset_position_history_point"),
        sa.CheckConstraint("source IN ('wialon','gtk')", name="ck_asset_position_history_source"),
        sa.CheckConstraint("lat BETWEEN -90 AND 90 AND lon BETWEEN -180 AND 180", name="ck_asset_position_history_range"),
    )
    op.create_index("ix_asset_position_history_asset_at", "asset_position_history", ["asset_id", "at"])


def downgrade() -> None:
    op.drop_table("asset_position_history")
