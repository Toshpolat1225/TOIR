"""Add editable daily mileage estimate for maintenance scheduling.

Revision ID: 0002_maintenance_settings
Revises: 0001_baseline
Create Date: 2026-10-16
"""

from alembic import op

revision = "0002_maintenance_settings"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS maintenance_settings (
            id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            daily_average_km numeric(10,2)
                CHECK (daily_average_km IS NULL OR daily_average_km > 0),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE maintenance_settings")
