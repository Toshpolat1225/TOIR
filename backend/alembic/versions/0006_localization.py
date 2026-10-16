"""Add locale catalogs and translations without translating legacy names.

Revision ID: 0006_localization
Revises: 0005_login_attempts
"""

from alembic import op

revision = "0006_localization"
down_revision = "0005_login_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TABLE fixed_asset_types (code text PRIMARY KEY, is_active boolean NOT NULL DEFAULT true)")
    op.execute("CREATE TABLE fixed_asset_statuses (code text PRIMARY KEY, is_active boolean NOT NULL DEFAULT true)")
    op.execute(
        "INSERT INTO fixed_asset_types(code) VALUES ('locomotive'), ('diesel'), ('wagon')"
    )
    op.execute(
        "INSERT INTO fixed_asset_statuses(code) VALUES ('operational'), ('maintenance'), ('repair'), ('out_of_service')"
    )
    op.execute(
        """
        CREATE TABLE department_translations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            department_id uuid NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
            locale text NOT NULL CHECK (locale IN ('uz-Latn','uz-Cyrl','ru')),
            name text NOT NULL,
            CONSTRAINT uq_department_translation_locale UNIQUE (department_id, locale)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE section_translations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            section_id uuid NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
            locale text NOT NULL CHECK (locale IN ('uz-Latn','uz-Cyrl','ru')),
            name text NOT NULL,
            CONSTRAINT uq_section_translation_locale UNIQUE (section_id, locale)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE work_type_translations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            work_type_id uuid NOT NULL REFERENCES work_types(id) ON DELETE CASCADE,
            locale text NOT NULL CHECK (locale IN ('uz-Latn','uz-Cyrl','ru')),
            name text NOT NULL,
            CONSTRAINT uq_work_type_translation_locale UNIQUE (work_type_id, locale)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE work_subtask_translations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            work_subtask_id uuid NOT NULL REFERENCES work_subtasks(id) ON DELETE CASCADE,
            locale text NOT NULL CHECK (locale IN ('uz-Latn','uz-Cyrl','ru')),
            name text NOT NULL,
            CONSTRAINT uq_work_subtask_translation_locale UNIQUE (work_subtask_id, locale)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE nomenclature_translations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            nomenclature_id uuid NOT NULL REFERENCES nomenclature(id) ON DELETE CASCADE,
            locale text NOT NULL CHECK (locale IN ('uz-Latn','uz-Cyrl','ru')),
            name text NOT NULL,
            CONSTRAINT uq_nomenclature_translation_locale UNIQUE (nomenclature_id, locale)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE fixed_asset_type_translations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            type_code text NOT NULL REFERENCES fixed_asset_types(code) ON DELETE CASCADE,
            locale text NOT NULL CHECK (locale IN ('uz-Latn','uz-Cyrl','ru')),
            name text NOT NULL,
            CONSTRAINT uq_fixed_asset_type_translation_locale UNIQUE (type_code, locale)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE fixed_asset_status_translations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            status_code text NOT NULL REFERENCES fixed_asset_statuses(code) ON DELETE CASCADE,
            locale text NOT NULL CHECK (locale IN ('uz-Latn','uz-Cyrl','ru')),
            name text NOT NULL,
            CONSTRAINT uq_fixed_asset_status_translation_locale UNIQUE (status_code, locale)
        )
        """
    )

    type_names = [
        ("locomotive", "Локомотив", "Lokomotiv", "Локомотив"),
        ("diesel", "Тепловоз", "Teplovoz", "Тепловоз"),
        ("wagon", "Вагон", "Vagon", "Вагон"),
    ]
    for code, ru, uz_latn, uz_cyrl in type_names:
        op.execute(
            "INSERT INTO fixed_asset_type_translations(type_code, locale, name) "
            f"VALUES ('{code}', 'ru', '{ru}'), ('{code}', 'uz-Latn', '{uz_latn}'), ('{code}', 'uz-Cyrl', '{uz_cyrl}')"
        )

    status_names = [
        ("operational", "В эксплуатации", "Foydalanishda", "Фойдаланишда"),
        ("maintenance", "На ТО", "Texnik xizmatda", "Техник хизматда"),
        ("repair", "Ремонт", "Ta’mirda", "Таъмирда"),
        ("out_of_service", "Выведен", "Foydalanishdan chiqarilgan", "Фойдаланишдан чиқарилган"),
    ]
    for code, ru, uz_latn, uz_cyrl in status_names:
        op.execute(
            "INSERT INTO fixed_asset_status_translations(status_code, locale, name) "
            f"VALUES ('{code}', 'ru', '{ru}'), ('{code}', 'uz-Latn', '{uz_latn}'), ('{code}', 'uz-Cyrl', '{uz_cyrl}')"
        )

    op.execute("ALTER TABLE fixed_assets DROP CONSTRAINT fixed_assets_asset_type_check")
    op.execute("ALTER TABLE fixed_assets DROP CONSTRAINT fixed_assets_status_check")
    op.execute(
        "ALTER TABLE fixed_assets ADD CONSTRAINT fk_fixed_assets_type_code "
        "FOREIGN KEY (asset_type) REFERENCES fixed_asset_types(code) ON UPDATE CASCADE ON DELETE RESTRICT"
    )
    op.execute(
        "ALTER TABLE fixed_assets ADD CONSTRAINT fk_fixed_assets_status_code "
        "FOREIGN KEY (status) REFERENCES fixed_asset_statuses(code) ON UPDATE CASCADE ON DELETE RESTRICT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE fixed_assets DROP CONSTRAINT fk_fixed_assets_type_code")
    op.execute("ALTER TABLE fixed_assets DROP CONSTRAINT fk_fixed_assets_status_code")
    op.execute("ALTER TABLE fixed_assets ADD CONSTRAINT fixed_assets_asset_type_check CHECK (asset_type IN ('locomotive','diesel','wagon'))")
    op.execute("ALTER TABLE fixed_assets ADD CONSTRAINT fixed_assets_status_check CHECK (status IN ('operational','maintenance','repair','out_of_service'))")
    for table in (
        "fixed_asset_status_translations",
        "fixed_asset_type_translations",
        "nomenclature_translations",
        "work_subtask_translations",
        "work_type_translations",
        "section_translations",
        "department_translations",
    ):
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP TABLE fixed_asset_statuses")
    op.execute("DROP TABLE fixed_asset_types")
