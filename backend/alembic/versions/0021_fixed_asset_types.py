"""Add fixed-asset types from the JSON register."""

from alembic import op

revision = "0021_fixed_asset_types"
down_revision = "0020_p7_permission_grants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO fixed_asset_types (code, color) VALUES
            ('tank_car', 'purple'),
            ('platform', 'green'),
            ('special_self_propelled', 'gray')
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO fixed_asset_type_translations (type_code, locale, name) VALUES
            ('tank_car', 'ru', 'Вагон-цистерна'),
            ('tank_car', 'uz-Latn', 'Sisterna vagoni'),
            ('tank_car', 'uz-Cyrl', 'Цистерна вагони'),
            ('platform', 'ru', 'Платформа'),
            ('platform', 'uz-Latn', 'Platforma'),
            ('platform', 'uz-Cyrl', 'Платформа'),
            ('special_self_propelled', 'ru', 'Специальный самоходный подвижной состав'),
            ('special_self_propelled', 'uz-Latn', 'Maxsus o‘ziyurar temir yo‘l tarkibi'),
            ('special_self_propelled', 'uz-Cyrl', 'Махсус ўзиюрар темир йўл таркиби')
        ON CONFLICT (type_code, locale) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM fixed_asset_type_translations
        WHERE type_code IN ('tank_car', 'platform', 'special_self_propelled')
        """
    )
    op.execute(
        """
        DELETE FROM fixed_asset_types
        WHERE code IN ('tank_car', 'platform', 'special_self_propelled')
        """
    )
