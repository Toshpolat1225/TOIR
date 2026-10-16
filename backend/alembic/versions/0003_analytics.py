"""Add analytics views and daily readiness snapshots.

Revision ID: 0003_analytics
Revises: 0002_maintenance_settings
Create Date: 2026-10-16
"""

from pathlib import Path

from alembic import op

revision = "0003_analytics"
down_revision = "0002_maintenance_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql_path = Path(__file__).with_name("0003_analytics.sql")
    for statement in sql_path.read_text(encoding="utf-8").split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    for view in (
        "maintenance_schedule",
        "fleet_health",
        "ai_insights_summary",
        "monthly_efficiency",
        "work_type_efficiency",
        "section_efficiency",
        "executive_summary",
        "work_order_tmc_details",
    ):
        op.execute(f"DROP VIEW IF EXISTS {view}")
    op.execute("DROP TABLE IF EXISTS daily_readiness_snapshots")
