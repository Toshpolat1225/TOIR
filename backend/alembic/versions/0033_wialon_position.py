"""Wialon unit position (latitude, longitude, time of the position fix) for the asset map.

Additive only: three nullable columns on `wialon_units`; nothing existing changes meaning. The Wialon request already
asked for the last message and position; only the speed and time were kept, the coordinates were dropped.

Revision ID: 0033_wialon_position
Revises: 0032_tirik_reja
"""
from alembic import op
import sqlalchemy as sa

revision = "0033_wialon_position"
down_revision = "0032_tirik_reja"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wialon_units", sa.Column("lat", sa.Numeric(10, 7), nullable=True))
    op.add_column("wialon_units", sa.Column("lon", sa.Numeric(10, 7), nullable=True))
    op.add_column("wialon_units", sa.Column("position_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_wialon_units_position_range",
        "wialon_units",
        "(lat IS NULL OR lat BETWEEN -90 AND 90) AND (lon IS NULL OR lon BETWEEN -180 AND 180)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_wialon_units_position_range", "wialon_units", type_="check")
    op.drop_column("wialon_units", "position_at")
    op.drop_column("wialon_units", "lon")
    op.drop_column("wialon_units", "lat")
