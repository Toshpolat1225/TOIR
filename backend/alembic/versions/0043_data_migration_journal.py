"""Migration journal: imported files (batches) and the values they wrote (items); view/manage permissions.

Additive only: two new tables and two permission codes. Nothing existing is changed.

Revision ID: 0043_data_migration_journal
Revises: 0042_auth01_no_local_passwords
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0043_data_migration_journal"
down_revision = "0042_auth01_no_local_passwords"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_migration_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("source_file", sa.Text(), nullable=False),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
    )
    op.create_table(
        "data_migration_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("data_migration_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("old_value", sa.Text()),
        sa.Column("new_value", sa.Text()),
        sa.Column("raw_value", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'applied'")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.CheckConstraint("status IN ('applied','reverted')", name="ck_data_migration_items_status"),
        sa.UniqueConstraint("batch_id", "asset_id", name="uq_data_migration_items_batch_asset"),
    )
    op.create_index("ix_data_migration_items_batch_status", "data_migration_items", ["batch_id", "status"])
    op.create_index("ix_data_migration_items_asset", "data_migration_items", ["asset_id"])
    op.execute(
        """
        INSERT INTO permissions(code, module, action, label) VALUES
            ('data_migration.view', 'data_migration', 'view', 'Data migration journal'),
            ('data_migration.manage', 'data_migration', 'manage_reference_data', 'Data migration journal')
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions(role, permission_code, granted) VALUES
            ('admin', 'data_migration.view', true), ('admin', 'data_migration.manage', true),
            ('operator', 'data_migration.view', true), ('operator', 'data_migration.manage', true),
            ('management', 'data_migration.view', true), ('management', 'data_migration.manage', false),
            ('master', 'data_migration.view', false), ('master', 'data_migration.manage', false)
        ON CONFLICT (role, permission_code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission_code IN ('data_migration.view','data_migration.manage')")
    op.execute("DELETE FROM permissions WHERE code IN ('data_migration.view','data_migration.manage')")
    op.drop_index("ix_data_migration_items_asset", table_name="data_migration_items")
    op.drop_index("ix_data_migration_items_batch_status", table_name="data_migration_items")
    op.drop_table("data_migration_items")
    op.drop_table("data_migration_batches")
