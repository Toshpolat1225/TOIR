"""Create a canonical link table for fixed assets and external sources."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0017_asset_source_links"
down_revision = "0016_gtk_mirror_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_source_links",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fixed_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("external_name", sa.Text()),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "link_method",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
        sa.Column(
            "linked_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("unlinked_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.Text()),
        sa.CheckConstraint(
            "source IN ('wialon','gtk','vesavoy','onec')",
            name="ck_asset_source_links_source",
        ),
        sa.CheckConstraint(
            "status IN ('active','ended')",
            name="ck_asset_source_links_status",
        ),
        sa.CheckConstraint(
            "link_method IN ('manual','migrated','import')",
            name="ck_asset_source_links_method",
        ),
    )
    op.create_index(
        "uq_asset_source_links_source_external_active",
        "asset_source_links",
        ["source", "external_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "uq_asset_source_links_asset_source_active",
        "asset_source_links",
        ["asset_id", "source"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_asset_source_links_asset_time",
        "asset_source_links",
        ["asset_id", "linked_at"],
    )

    op.execute(
        """
        INSERT INTO asset_source_links
            (asset_id, source, external_id, status, link_method, linked_at)
        SELECT id, 'wialon', wialon_id, 'active', 'migrated', now()
        FROM fixed_assets
        WHERE wialon_id IS NOT NULL AND btrim(wialon_id) <> ''
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO asset_source_links
            (asset_id, source, external_id, status, link_method, linked_at)
        SELECT id, 'gtk', gtk_id, 'active', 'migrated', now()
        FROM fixed_assets
        WHERE gtk_id IS NOT NULL AND btrim(gtk_id) <> ''
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO permissions(code, module, action, label) VALUES
            ('asset_links.view', 'asset_links', 'view', 'External asset links'),
            ('asset_links.manage', 'asset_links', 'manage_reference_data', 'External asset links')
        ON CONFLICT (code) DO NOTHING
        """
    )
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
            ('master', 'asset_links.manage', false)
        ON CONFLICT (role, permission_code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions "
        "WHERE permission_code IN ('asset_links.view','asset_links.manage')"
    )
    op.execute(
        "DELETE FROM permissions "
        "WHERE code IN ('asset_links.view','asset_links.manage')"
    )
    op.drop_index(
        "ix_asset_source_links_asset_time", table_name="asset_source_links"
    )
    op.drop_index(
        "uq_asset_source_links_asset_source_active",
        table_name="asset_source_links",
    )
    op.drop_index(
        "uq_asset_source_links_source_external_active",
        table_name="asset_source_links",
    )
    op.drop_table("asset_source_links")
