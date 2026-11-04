"""Add normalized fixed-asset passport fields and model catalog."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.services.asset_passport import plan_passport_backfill

revision = "0018_asset_passport"
down_revision = "0017_asset_source_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_models",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_normalized", sa.Text(), nullable=False),
        sa.Column(
            "asset_type",
            sa.Text(),
            sa.ForeignKey(
                "fixed_asset_types.code",
                onupdate="CASCADE",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("series", sa.Text()),
        sa.UniqueConstraint(
            "name_normalized", name="uq_asset_models_name_normalized"
        ),
    )
    op.add_column("fixed_assets", sa.Column("number", sa.Text(), nullable=True))
    op.add_column(
        "fixed_assets", sa.Column("number_normalized", sa.Text(), nullable=True)
    )
    op.add_column(
        "fixed_assets", sa.Column("serial_number", sa.Text(), nullable=True)
    )
    op.add_column(
        "fixed_assets",
        sa.Column(
            "model_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("asset_models.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column(
        "fixed_assets",
        sa.Column("accounting_inv_number", sa.Text(), nullable=True),
    )
    op.add_column(
        "fixed_assets",
        sa.Column(
            "org_unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sections.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "fixed_assets", sa.Column("commissioned_at", sa.Date(), nullable=True)
    )
    op.add_column(
        "fixed_assets", sa.Column("decommissioned_at", sa.Date(), nullable=True)
    )
    op.add_column(
        "fixed_assets",
        sa.Column(
            "inv_number_is_provisional",
            sa.Boolean(),
            nullable=True,
            server_default=sa.text("false"),
        ),
    )

    op.drop_constraint(
        "fixed_assets_inv_number_key", "fixed_assets", type_="unique"
    )
    op.create_index("ix_fixed_assets_model_id", "fixed_assets", ["model_id"])
    op.create_index("ix_fixed_assets_org_unit_id", "fixed_assets", ["org_unit_id"])
    op.create_index(
        "uq_fixed_assets_inv_number_real",
        "fixed_assets",
        ["inv_number"],
        unique=True,
        postgresql_where=sa.text("inv_number_is_provisional IS FALSE"),
    )
    op.create_index(
        "uq_fixed_assets_accounting_inv_number",
        "fixed_assets",
        ["accounting_inv_number"],
        unique=True,
        postgresql_where=sa.text("accounting_inv_number IS NOT NULL"),
    )

    bind = op.get_bind()
    existing_assets = bind.execute(
        sa.text(
            """
            SELECT id, name, series, asset_type, inv_number, comm_date
            FROM fixed_assets
            ORDER BY id
            """
        )
    ).mappings().all()
    model_rows, asset_rows = plan_passport_backfill(existing_assets)
    model_ids: dict[str, object] = {}
    for model in model_rows:
        inserted_id = bind.execute(
            postgresql.insert(sa.table(
                "asset_models",
                sa.column("id", postgresql.UUID(as_uuid=True)),
                sa.column("name", sa.Text()),
                sa.column("name_normalized", sa.Text()),
                sa.column("asset_type", sa.Text()),
                sa.column("series", sa.Text()),
            ))
            .values(**model)
            .on_conflict_do_nothing(index_elements=["name_normalized"])
            .returning(sa.column("id"))
        ).scalar_one_or_none()
        if inserted_id is None:
            inserted_id = bind.execute(
                sa.text(
                    "SELECT id FROM asset_models WHERE name_normalized = :normalized"
                ),
                {"normalized": model["name_normalized"]},
            ).scalar_one()
        model_ids[model["name_normalized"]] = inserted_id

    for row in asset_rows:
        bind.execute(
            sa.text(
                """
                UPDATE fixed_assets
                SET number = :number,
                    number_normalized = :number_normalized,
                    commissioned_at = :commissioned_at,
                    inv_number_is_provisional = :is_provisional,
                    model_id = :model_id
                WHERE id = :id
                """
            ),
            {
                "id": row["id"],
                "number": row["number"],
                "number_normalized": row["number_normalized"],
                "commissioned_at": row["commissioned_at"],
                "is_provisional": row["inv_number_is_provisional"],
                "model_id": (
                    model_ids.get(row["model_normalized"])
                    if row["model_normalized"] is not None
                    else None
                ),
            },
        )

    bind.execute(
        sa.text(
            """
            WITH unique_sections AS (
                SELECT id, name
                FROM sections
                WHERE is_archived IS FALSE
                  AND name IN (
                      SELECT name
                      FROM sections
                      WHERE is_archived IS FALSE
                      GROUP BY name
                      HAVING count(*) = 1
                  )
            )
            UPDATE fixed_assets AS asset
            SET org_unit_id = section.id
            FROM unique_sections AS section
            WHERE asset.org_unit_id IS NULL
              AND asset.depot = section.name
            """
        )
    )

    duplicate_count = bind.execute(
        sa.text(
            """
            SELECT count(*)
            FROM (
                SELECT asset_type, model_id, number_normalized
                FROM fixed_assets
                WHERE model_id IS NOT NULL
                  AND number_normalized IS NOT NULL
                GROUP BY asset_type, model_id, number_normalized
                HAVING count(*) > 1
            ) AS duplicates
            """
        )
    ).scalar_one()
    if duplicate_count:
        op.create_index(
            "ix_fixed_assets_type_model_number",
            "fixed_assets",
            ["asset_type", "model_id", "number_normalized"],
        )
    else:
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

    op.create_check_constraint(
        "ck_fixed_assets_year_built_min",
        "fixed_assets",
        "year_built IS NULL OR year_built >= 1900",
        postgresql_not_valid=True,
    )
    op.create_check_constraint(
        "ck_fixed_assets_commissioned_at_year_built",
        "fixed_assets",
        "CASE WHEN commissioned_at IS NULL OR year_built IS NULL "
        "OR year_built < 1 OR year_built > 9999 THEN true "
        "ELSE commissioned_at >= make_date(year_built, 1, 1) END",
        postgresql_not_valid=True,
    )
    op.create_check_constraint(
        "ck_fixed_assets_decommissioned_at_commissioned_at",
        "fixed_assets",
        "decommissioned_at IS NULL OR commissioned_at IS NULL "
        "OR decommissioned_at >= commissioned_at",
        postgresql_not_valid=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    duplicate_inventory = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM fixed_assets
            GROUP BY inv_number
            HAVING count(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate_inventory is not None:
        raise RuntimeError(
            "Cannot downgrade asset passport while duplicate inventory numbers exist"
        )

    indexes = {
        index["name"]
        for index in sa.inspect(bind).get_indexes("fixed_assets")
    }
    if "uq_fixed_assets_active_model_number" in indexes:
        op.drop_index(
            "uq_fixed_assets_active_model_number", table_name="fixed_assets"
        )
    if "ix_fixed_assets_type_model_number" in indexes:
        op.drop_index(
            "ix_fixed_assets_type_model_number", table_name="fixed_assets"
        )
    op.drop_constraint(
        "ck_fixed_assets_decommissioned_at_commissioned_at",
        "fixed_assets",
        type_="check",
    )
    op.drop_constraint(
        "ck_fixed_assets_commissioned_at_year_built",
        "fixed_assets",
        type_="check",
    )
    op.drop_constraint(
        "ck_fixed_assets_year_built_min", "fixed_assets", type_="check"
    )
    op.drop_index(
        "uq_fixed_assets_accounting_inv_number", table_name="fixed_assets"
    )
    op.drop_index("uq_fixed_assets_inv_number_real", table_name="fixed_assets")
    op.drop_index("ix_fixed_assets_org_unit_id", table_name="fixed_assets")
    op.drop_index("ix_fixed_assets_model_id", table_name="fixed_assets")
    op.create_unique_constraint(
        "fixed_assets_inv_number_key", "fixed_assets", ["inv_number"]
    )
    for column in (
        "inv_number_is_provisional",
        "decommissioned_at",
        "commissioned_at",
        "org_unit_id",
        "accounting_inv_number",
        "model_id",
        "serial_number",
        "number_normalized",
        "number",
    ):
        op.drop_column("fixed_assets", column)
    op.drop_table("asset_models")
