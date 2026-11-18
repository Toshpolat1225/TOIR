"""GPS: the Wialon odometer as the third opinion of a day, and a heartbeat for running GTK GPS synchronisations.

Additive only: nullable columns.

Revision ID: 0039_gps_odometer_heartbeat
Revises: 0038_gps_analytics
"""
from alembic import op
import sqlalchemy as sa

revision = "0039_gps_odometer_heartbeat"
down_revision = "0038_gps_analytics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gps_day_assessment", sa.Column("odo_m", sa.Integer))
    op.add_column("gps_day_assessment", sa.Column("odo_agrees", sa.Boolean))
    op.add_column("gtk_gps_runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("gtk_gps_runs", "heartbeat_at")
    op.drop_column("gps_day_assessment", "odo_agrees")
    op.drop_column("gps_day_assessment", "odo_m")
