"""Reconcile source-link and conflict permission grants."""

from alembic import op

revision = "0020_p7_permission_grants"
down_revision = "0019_asset_field_changes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO role_permissions(role, permission_code, granted)
        VALUES
            ('admin', 'asset_links.view', true),
            ('operator', 'asset_links.view', true),
            ('management', 'asset_links.view', true),
            ('master', 'asset_links.view', false),
            ('admin', 'asset_links.manage', true),
            ('operator', 'asset_links.manage', true),
            ('management', 'asset_links.manage', false),
            ('master', 'asset_links.manage', false),
            ('admin', 'asset_conflicts.manage', true),
            ('operator', 'asset_conflicts.manage', true),
            ('management', 'asset_conflicts.manage', false),
            ('master', 'asset_conflicts.manage', false)
        ON CONFLICT (role, permission_code)
        DO UPDATE SET granted = EXCLUDED.granted
        """
    )


def downgrade() -> None:
    pass
