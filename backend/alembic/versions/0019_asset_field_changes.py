"""Add the fixed-asset field change journal."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0019_asset_field_changes"
down_revision = "0018_asset_passport"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_field_changes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fixed_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field", sa.String(100), nullable=False),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "resolved_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "kind IN ('auto_fill','conflict','manual')",
            name="ck_asset_field_changes_kind",
        ),
        sa.CheckConstraint(
            "status IN ('applied','pending','accepted','rejected')",
            name="ck_asset_field_changes_status",
        ),
    )
    op.create_index(
        "ix_asset_field_changes_status_created",
        "asset_field_changes",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_asset_field_changes_asset_field_status",
        "asset_field_changes",
        ["asset_id", "field", "status"],
    )
    op.execute(
        """
        INSERT INTO permissions(code, module, action, label)
        VALUES (
            'asset_conflicts.manage',
            'asset_conflicts',
            'manage_reference_data',
            'Asset field conflicts'
        )
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions(role, permission_code, granted)
        VALUES
            ('admin', 'asset_conflicts.manage', true),
            ('operator', 'asset_conflicts.manage', true),
            ('management', 'asset_conflicts.manage', false),
            ('master', 'asset_conflicts.manage', false)
        ON CONFLICT (role, permission_code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions "
        "WHERE permission_code = 'asset_conflicts.manage'"
    )
    op.execute(
        "DELETE FROM permissions WHERE code = 'asset_conflicts.manage'"
    )
    op.drop_index(
        "ix_asset_field_changes_asset_field_status",
        table_name="asset_field_changes",
    )
    op.drop_index(
        "ix_asset_field_changes_status_created",
        table_name="asset_field_changes",
    )
    op.drop_table("asset_field_changes")
