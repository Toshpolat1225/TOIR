"""Align fixed-asset indexes with the non-unique asset identity contract."""

from alembic import op

revision = "0023_canonical_asset_indexes"
down_revision = "0022_asset_number_dupes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_fixed_assets_inv_number_real")
    op.execute("DROP INDEX IF EXISTS uq_fixed_assets_active_model_number")
    op.execute("DROP INDEX IF EXISTS ix_fixed_assets_type_model_number")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fixed_assets_inv_number
        ON fixed_assets (inv_number)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fixed_assets_type_model_serial
        ON fixed_assets (asset_type, model_id, serial_number)
        WHERE model_id IS NOT NULL AND serial_number IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_fixed_assets_type_model_serial")
