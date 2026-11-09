"""Move fixed-asset display and legacy fields out of the database table."""

from alembic import op

revision = "0024_asset_column_contract"
down_revision = "0023_canonical_asset_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE fixed_assets
        SET serial_number = COALESCE(serial_number, number),
            section_id = COALESCE(section_id, org_unit_id),
            commissioned_at = COALESCE(commissioned_at, comm_date)
        """
    )
    op.execute(
        """
        UPDATE asset_models model
        SET series = (
            SELECT btrim(assets.series)
            FROM fixed_assets assets
            WHERE assets.model_id = model.id
              AND assets.series IS NOT NULL
            ORDER BY assets.id
            LIMIT 1
        )
        WHERE model.series IS NULL
          AND EXISTS (
              SELECT 1
              FROM fixed_assets assets
              WHERE assets.model_id = model.id
                AND assets.series IS NOT NULL
          )
        """
    )
    op.execute(
        """
        INSERT INTO asset_models (name, name_normalized, asset_type, series)
        SELECT min(btrim(assets.series)),
               regexp_replace(
                   translate(
                       lower(btrim(assets.series)),
                       'abcdehkmoptxy',
                       'авсдэнкмоптху'
                   ),
                   '[^[:alnum:]]',
                   '',
                   'g'
               ),
               assets.asset_type,
               min(btrim(assets.series))
        FROM fixed_assets assets
        WHERE assets.model_id IS NULL
          AND nullif(btrim(assets.series), '') IS NOT NULL
        GROUP BY assets.asset_type,
                 regexp_replace(
                     translate(
                         lower(btrim(assets.series)),
                         'abcdehkmoptxy',
                         'авсдэнкмоптху'
                     ),
                     '[^[:alnum:]]',
                     '',
                     'g'
                 )
        ON CONFLICT (name_normalized) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE fixed_assets assets
        SET model_id = model.id
        FROM asset_models model
        WHERE assets.model_id IS NULL
          AND assets.series IS NOT NULL
          AND model.asset_type = assets.asset_type
          AND model.name_normalized = regexp_replace(
              translate(
                  lower(btrim(assets.series)),
                  'abcdehkmoptxy',
                  'авсдэнкмоптху'
              ),
              '[^[:alnum:]]',
              '',
              'g'
          )
        """
    )
    op.execute(
        """
        UPDATE fixed_assets assets
        SET section_id = candidate.id
        FROM (
            SELECT name AS section_name, min(id::text)::uuid AS id
            FROM sections
            GROUP BY name
            HAVING count(*) = 1
        ) candidate
        WHERE assets.section_id IS NULL
          AND assets.depot = candidate.section_name
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fixed_asset_display_name(
            asset_type text,
            serial_number text,
            inv_number text
        ) RETURNS text
        LANGUAGE sql
        STABLE
        AS $$
            SELECT COALESCE(
                (
                    SELECT fat.name
                    FROM fixed_asset_type_translations fat
                    WHERE fat.type_code = $1 AND fat.locale = 'ru'
                    LIMIT 1
                ),
                $1
            ) || ' ' || COALESCE($2, '') || '-' || $3
        $$;
        """
    )
    op.execute(
        """
        DO $$
        DECLARE
            view_name text;
            view_definition text;
            display_name text :=
                'public.fixed_asset_display_name(fa.asset_type, fa.serial_number, fa.inv_number)';
        BEGIN
            FOREACH view_name IN ARRAY ARRAY[
                'work_order_tmc_details',
                'executive_summary',
                'maintenance_schedule'
            ] LOOP
                IF to_regclass('public.' || view_name) IS NOT NULL THEN
                    SELECT pg_get_viewdef(
                        to_regclass('public.' || view_name), true
                    ) INTO view_definition;
                    view_definition := replace(view_definition, 'fa.name', display_name);
                    EXECUTE format(
                        'CREATE OR REPLACE VIEW public.%I AS %s',
                        view_name,
                        view_definition
                    );
                END IF;
            END LOOP;
        END
        $$;
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_assets_series")
    op.execute("DROP INDEX IF EXISTS ix_fixed_assets_org_unit_id")
    op.execute(
        """
        ALTER TABLE fixed_assets
            DROP COLUMN IF EXISTS name,
            DROP COLUMN IF EXISTS series,
            DROP COLUMN IF EXISTS depot,
            DROP COLUMN IF EXISTS number,
            DROP COLUMN IF EXISTS number_normalized,
            DROP COLUMN IF EXISTS org_unit_id,
            DROP COLUMN IF EXISTS comm_date
        """
    )


def downgrade() -> None:
    raise RuntimeError(
        "The fixed-asset column contract migration is irreversible; "
        "restore a backup to recover the removed legacy columns."
    )
