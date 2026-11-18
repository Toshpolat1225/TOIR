"""GPS analytics: per-day assessment of both trackers (cause, fused distance, confidence) and wagon segments with distance candidates.

Additive only: two new tables.

Revision ID: 0038_gps_analytics
Revises: 0037_gtk_gps
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0038_gps_analytics"
down_revision = "0037_gtk_gps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gps_day_assessment",
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fixed_assets.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("day", sa.Date, primary_key=True),
        sa.Column("wialon_m", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("wialon_points", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("gtk_m", sa.Integer),
        sa.Column("gtk_points", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("gtk_raw_points", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("gtk_final", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("gtk_collected", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("verdict", sa.Text, nullable=False),
        sa.Column("ratio", sa.Numeric(8, 3)),
        sa.Column("diff_m", sa.Integer),
        sa.Column("fused_m", sa.Integer),
        sa.Column("unknown_gap_m", sa.Integer),
        sa.Column("wialon_cov_h", sa.Numeric(5, 2)),
        sa.Column("gtk_cov_h", sa.Numeric(5, 2)),
        sa.Column("wialon_gap_h", sa.Numeric(5, 2)),
        sa.Column("gtk_gap_h", sa.Numeric(5, 2)),
        sa.Column("cause", sa.Text, nullable=False),
        sa.Column("confidence", sa.Numeric(3, 2)),
        sa.Column("idle_events", sa.Integer),
        sa.Column("is_final", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("algorithm_version", sa.Text, nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_gps_day_assessment_day", "gps_day_assessment", ["day"])
    op.create_table(
        "gps_wagon_segments",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("wagon_asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fixed_assets.id", ondelete="SET NULL")),
        sa.Column("carriage_gtk_id", sa.Integer, nullable=False),
        sa.Column("train_gtk_id", sa.Integer, nullable=False),
        sa.Column("loco_asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fixed_assets.id", ondelete="SET NULL")),
        sa.Column("loco_gtk_id", sa.Integer),
        sa.Column("period_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_open", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("km_odometer", sa.Numeric(10, 3)),
        sa.Column("km_wialon", sa.Numeric(10, 3)),
        sa.Column("km_gtk", sa.Numeric(10, 3)),
        sa.Column("km_fused", sa.Numeric(10, 3)),
        sa.Column("selected_km", sa.Numeric(10, 3)),
        sa.Column("basis", sa.Text, nullable=False),
        sa.Column("confidence", sa.Text, nullable=False),
        sa.Column("coverage", sa.Numeric(4, 3)),
        sa.Column("flags", postgresql.JSONB),
        sa.Column("algorithm_version", sa.Text, nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("carriage_gtk_id", "train_gtk_id", "period_from", name="uq_gps_wagon_segments_key"),
    )
    op.create_index("ix_gps_wagon_segments_wagon", "gps_wagon_segments", ["wagon_asset_id", "period_from"])
    op.create_index("ix_gps_wagon_segments_loco", "gps_wagon_segments", ["loco_asset_id", "period_from"])


def downgrade() -> None:
    op.drop_table("gps_wagon_segments")
    op.drop_table("gps_day_assessment")
