"""Add application audit logs with 365-day retention support.

Revision ID: 0026_audit_logs
Revises: 0025_russian_only
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0026_audit_logs"
down_revision = "0025_russian_only"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("actor_name", sa.Text(), nullable=True),
        sa.Column("module", sa.Text(), nullable=False),
        sa.Column("route", sa.Text(), nullable=False),
        sa.Column("object_type", sa.Text(), nullable=True),
        sa.Column("object_id", sa.Text(), nullable=True),
        sa.Column("object_label", sa.Text(), nullable=True),
        sa.Column("old_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('create','update','delete','login','logout','other')",
            name="ck_audit_logs_action",
        ),
        sa.CheckConstraint(
            "actor_type IN ('user','system','anonymous')",
            name="ck_audit_logs_actor_type",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index(
        "ix_audit_logs_actor_created",
        "audit_logs",
        ["actor_user_id", "created_at"],
    )
    op.create_index(
        "ix_audit_logs_action_created", "audit_logs", ["action", "created_at"]
    )
    op.create_index(
        "ix_audit_logs_module_created", "audit_logs", ["module", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_module_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")
