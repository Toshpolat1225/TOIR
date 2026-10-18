"""Allow managed asset catalogs and retain existing status behavior.

Revision ID: 0007_asset_catalog_management
Revises: 0006_localization
"""
from alembic import op

revision = "0007_asset_catalog_management"
down_revision = "0006_localization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE UNIQUE INDEX uq_fixed_asset_type_translation_name ON fixed_asset_type_translations(locale, lower(name))")
    op.execute("CREATE UNIQUE INDEX uq_fixed_asset_status_translation_name ON fixed_asset_status_translations(locale, lower(name))")
    op.execute("ALTER TABLE fixed_asset_types ADD COLUMN color text NOT NULL DEFAULT 'blue'")
    op.execute("ALTER TABLE fixed_asset_statuses ADD COLUMN behavior text NOT NULL DEFAULT 'operational'")
    op.execute("ALTER TABLE fixed_asset_statuses ADD COLUMN color text NOT NULL DEFAULT 'green'")
    op.execute("ALTER TABLE fixed_asset_statuses ADD CONSTRAINT ck_fixed_asset_status_behavior CHECK (behavior IN ('operational','maintenance','repair','out_of_service'))")
    op.execute("ALTER TABLE fixed_asset_types ADD CONSTRAINT ck_fixed_asset_type_color CHECK (color IN ('blue','green','amber','orange','red','gray','purple'))")
    op.execute("ALTER TABLE fixed_asset_statuses ADD CONSTRAINT ck_fixed_asset_status_color CHECK (color IN ('blue','green','amber','orange','red','gray','purple'))")
    op.execute("UPDATE fixed_asset_statuses SET behavior = code WHERE code IN ('operational','maintenance','repair','out_of_service')")
    op.execute("UPDATE fixed_asset_statuses SET color = CASE behavior WHEN 'operational' THEN 'green' WHEN 'maintenance' THEN 'amber' WHEN 'repair' THEN 'orange' ELSE 'gray' END")
    op.execute("UPDATE fixed_asset_types SET color = CASE code WHEN 'locomotive' THEN 'blue' WHEN 'diesel' THEN 'orange' ELSE 'gray' END")


def downgrade() -> None:
    op.execute("DROP INDEX uq_fixed_asset_status_translation_name")
    op.execute("DROP INDEX uq_fixed_asset_type_translation_name")
    op.execute("ALTER TABLE fixed_asset_statuses DROP CONSTRAINT ck_fixed_asset_status_color")
    op.execute("ALTER TABLE fixed_asset_types DROP CONSTRAINT ck_fixed_asset_type_color")
    op.execute("ALTER TABLE fixed_asset_statuses DROP CONSTRAINT ck_fixed_asset_status_behavior")
    op.execute("ALTER TABLE fixed_asset_statuses DROP COLUMN color")
    op.execute("ALTER TABLE fixed_asset_statuses DROP COLUMN behavior")
    op.execute("ALTER TABLE fixed_asset_types DROP COLUMN color")
