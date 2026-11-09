"""Restrict reference translations to Russian.

Revision ID: 0025_russian_only
Revises: 0024_asset_column_contract
"""

from alembic import op

revision = "0025_russian_only"
down_revision = "0024_asset_column_contract"
branch_labels = None
depends_on = None

TABLES = {
    "department_translations": "ck_department_translation_locale",
    "section_translations": "ck_section_translation_locale",
    "work_type_translations": "ck_work_type_translation_locale",
    "work_subtask_translations": "ck_work_subtask_translation_locale",
    "nomenclature_translations": "ck_nomenclature_translation_locale",
    "fixed_asset_type_translations": "ck_fixed_asset_type_translation_locale",
    "fixed_asset_status_translations": "ck_fixed_asset_status_translation_locale",
}


def upgrade() -> None:
    for table, constraint in TABLES.items():
        op.execute(f"DELETE FROM {table} WHERE locale <> 'ru'")
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}")
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_locale_check")
        op.create_check_constraint(constraint, table, "locale = 'ru'")


def downgrade() -> None:
    for table, constraint in TABLES.items():
        op.drop_constraint(constraint, table, type_="check")
        op.create_check_constraint(
            constraint,
            table,
            "locale IN ('uz-Latn', 'uz-Cyrl', 'ru')",
        )
