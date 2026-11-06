"""Allow duplicate source-provided asset numbers."""

import sqlalchemy as sa
from alembic import op

revision = "0022_asset_number_dupes"
down_revision = "0021_fixed_asset_types"
branch_labels = None
depends_on = None


def _index_names() -> set[str]:
    return {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes("fixed_assets")
    }


def upgrade() -> None:
    indexes = _index_names()
    for name in (
        "uq_fixed_assets_inv_number_real",
        "uq_fixed_assets_active_model_number",
        "ix_fixed_assets_inv_number",
        "ix_fixed_assets_type_model_number",
    ):
        if name in indexes:
            op.drop_index(name, table_name="fixed_assets")

    op.create_index(
        "ix_fixed_assets_inv_number",
        "fixed_assets",
        ["inv_number"],
        unique=False,
    )
    op.create_index(
        "ix_fixed_assets_type_model_number",
        "fixed_assets",
        ["asset_type", "model_id", "number_normalized"],
        unique=False,
        postgresql_where=sa.text(
            "model_id IS NOT NULL AND number_normalized IS NOT NULL"
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    duplicate_inventory = bind.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM fixed_assets
                WHERE inv_number_is_provisional IS FALSE
                GROUP BY inv_number
                HAVING count(*) > 1
            )
            """
        )
    ).scalar_one()
    duplicate_numbers = bind.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM fixed_assets
                WHERE decommissioned_at IS NULL
                  AND model_id IS NOT NULL
                  AND number_normalized IS NOT NULL
                GROUP BY asset_type, model_id, number_normalized
                HAVING count(*) > 1
            )
            """
        )
    ).scalar_one()
    if duplicate_inventory or duplicate_numbers:
        raise RuntimeError(
            "Cannot restore unique asset-number indexes while duplicates exist."
        )

    indexes = _index_names()
    for name in (
        "ix_fixed_assets_inv_number",
        "ix_fixed_assets_type_model_number",
    ):
        if name in indexes:
            op.drop_index(name, table_name="fixed_assets")

    op.create_index(
        "uq_fixed_assets_inv_number_real",
        "fixed_assets",
        ["inv_number"],
        unique=True,
        postgresql_where=sa.text("inv_number_is_provisional IS FALSE"),
    )
    op.create_index(
        "uq_fixed_assets_active_model_number",
        "fixed_assets",
        ["asset_type", "model_id", "number_normalized"],
        unique=True,
        postgresql_where=sa.text(
            "decommissioned_at IS NULL AND model_id IS NOT NULL "
            "AND number_normalized IS NOT NULL"
        ),
    )
