"""Maintenance plan: manually rescheduled date (drag and drop on the Gantt chart).

The system recomputes `scheduled_date` of every scheduled plan whenever mileage changes. A planner
who cannot physically take the unit in on the recommended day moves the date by hand; the flag
keeps that decision from being overwritten, and the original recommendation stays visible.

Revision ID: 0031_plan_manual_date
Revises: 0030_user_auth_source
"""
from alembic import op
import sqlalchemy as sa

revision = "0031_plan_manual_date"
down_revision = "0030_user_auth_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "maintenance_plan",
        sa.Column(
            "scheduled_date_manual",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column("maintenance_plan", sa.Column("recommended_date", sa.Date(), nullable=True))
    op.add_column("maintenance_plan", sa.Column("reschedule_reason", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_maintenance_plan_reschedule_reason_len",
        "maintenance_plan",
        "reschedule_reason IS NULL OR char_length(reschedule_reason) <= 500",
    )
    op.create_check_constraint(
        "ck_maintenance_plan_manual_consistency",
        "maintenance_plan",
        "scheduled_date_manual OR (recommended_date IS NULL AND reschedule_reason IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_maintenance_plan_manual_consistency", "maintenance_plan", type_="check")
    op.drop_constraint("ck_maintenance_plan_reschedule_reason_len", "maintenance_plan", type_="check")
    op.drop_column("maintenance_plan", "reschedule_reason")
    op.drop_column("maintenance_plan", "recommended_date")
    op.drop_column("maintenance_plan", "scheduled_date_manual")
