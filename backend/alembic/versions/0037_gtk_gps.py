"""GTK's own GPS: live unit state, per-day distance, sync log; the track points reuse asset_position_history (source 'gtk_gps').

Additive: three new tables and the source CHECK of asset_position_history gains one value.

Revision ID: 0037_gtk_gps
Revises: 0036_position_history
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0037_gtk_gps"
down_revision = "0036_position_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_asset_position_history_source", "asset_position_history", type_="check")
    op.create_check_constraint("ck_asset_position_history_source", "asset_position_history", "source IN ('wialon','gtk','gtk_gps')")
    op.create_table(
        "gtk_gps_units",
        sa.Column("gtk_id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("name", sa.Text),
        sa.Column("garage_number", sa.Text),
        sa.Column("model_name", sa.Text),
        sa.Column("vehicle_type_id", sa.Integer),
        sa.Column("enterprise_id", sa.Integer),
        sa.Column("lat", sa.Numeric(10, 7)),
        sa.Column("lon", sa.Numeric(10, 7)),
        sa.Column("speed", sa.Numeric(6, 2)),
        sa.Column("course", sa.Numeric(6, 2)),
        sa.Column("height", sa.Numeric(8, 2)),
        sa.Column("position_at", sa.DateTime(timezone=True)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("(lat IS NULL OR lat BETWEEN -90 AND 90) AND (lon IS NULL OR lon BETWEEN -180 AND 180)", name="ck_gtk_gps_units_range"),
    )
    op.create_table(
        "gtk_gps_days",
        sa.Column("gtk_id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("day", sa.Date, primary_key=True),
        sa.Column("distance_m", sa.Integer),
        sa.Column("points", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("first_at", sa.DateTime(timezone=True)),
        sa.Column("last_at", sa.DateTime(timezone=True)),
        sa.Column("events", postgresql.JSONB),
        sa.Column("is_final", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_gtk_gps_days_day", "gtk_gps_days", ["day"])
    op.create_table(
        "gtk_gps_runs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("units", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("tracks_ok", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("tracks_failed", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("points_stored", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("error_code", sa.Text),
        sa.CheckConstraint("status IN ('success','partial','failed')", name="ck_gtk_gps_runs_status"),
    )
    op.create_index("ix_gtk_gps_runs_started_at", "gtk_gps_runs", ["started_at"])


def downgrade() -> None:
    op.drop_table("gtk_gps_runs")
    op.drop_table("gtk_gps_days")
    op.drop_table("gtk_gps_units")
    op.execute("DELETE FROM asset_position_history WHERE source = 'gtk_gps'")
    op.drop_constraint("ck_asset_position_history_source", "asset_position_history", type_="check")
    op.create_check_constraint("ck_asset_position_history_source", "asset_position_history", "source IN ('wialon','gtk')")
