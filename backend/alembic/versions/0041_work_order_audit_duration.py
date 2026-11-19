"""Work orders: actual start/end and last editor; work types: standard duration.

Additive only: nullable columns. Existing rows stay NULL (nothing is invented).

Revision ID: 0041_work_order_audit_duration
Revises: 0040_assistant
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0041_work_order_audit_duration"
down_revision = "0040_assistant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("work_types", sa.Column("duration_hours", sa.Numeric(7, 2)))
    op.create_check_constraint(
        "work_types_duration_hours_check", "work_types", "duration_hours IS NULL OR duration_hours > 0"
    )
    op.add_column("work_orders", sa.Column("actual_start", sa.DateTime(timezone=True)))
    op.add_column("work_orders", sa.Column("actual_end", sa.DateTime(timezone=True)))
    op.add_column(
        "work_orders",
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
    )


def downgrade() -> None:
    op.drop_column("work_orders", "updated_by")
    op.drop_column("work_orders", "actual_end")
    op.drop_column("work_orders", "actual_start")
    op.drop_constraint("work_types_duration_hours_check", "work_types", type_="check")
    op.drop_column("work_types", "duration_hours")
