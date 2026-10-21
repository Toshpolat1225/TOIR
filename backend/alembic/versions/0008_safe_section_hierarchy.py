"""Enforce safe typed hierarchy rules and preserve legacy section identifiers.

Revision ID: 0008_safe_section_hierarchy
Revises: 0007_section_hierarchy
"""

from alembic import op

revision = "0008_safe_section_hierarchy"
down_revision = "0007_section_hierarchy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM sections
                WHERE unit_type NOT IN ('department', 'division', 'section', 'team')
            ) THEN
                RAISE EXCEPTION 'Cannot upgrade: sections contain an unsupported unit_type';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM sections child
                JOIN sections parent ON parent.id = child.parent_id
                WHERE NOT (
                    (child.unit_type = 'division' AND parent.unit_type IN ('department', 'division'))
                    OR (child.unit_type = 'section' AND parent.unit_type IN ('department', 'division', 'section'))
                    OR (child.unit_type = 'team' AND parent.unit_type IN ('division', 'section', 'team'))
                )
            ) THEN
                RAISE EXCEPTION 'Cannot upgrade: sections contain invalid typed parent-child relationships';
            END IF;

            IF EXISTS (
                WITH RECURSIVE ancestors(start_id, current_id, parent_id, visited, has_cycle) AS (
                    SELECT id, id, parent_id, ARRAY[id], false
                    FROM sections
                    UNION ALL
                    SELECT a.start_id, parent.id, parent.parent_id,
                           a.visited || parent.id, parent.id = ANY(a.visited)
                    FROM ancestors a
                    JOIN sections parent ON parent.id = a.parent_id
                    WHERE NOT a.has_cycle
                )
                SELECT 1 FROM ancestors WHERE has_cycle
            ) THEN
                RAISE EXCEPTION 'Cannot upgrade: sections contain a parent cycle';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM sections child
                JOIN sections parent ON parent.id = child.parent_id
                WHERE parent.is_archived AND NOT child.is_archived
            ) THEN
                RAISE EXCEPTION 'Cannot upgrade: active sections have an archived parent';
            END IF;
        END;
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_sections_unit_type_supported'
                  AND conrelid = 'sections'::regclass
            ) THEN
                ALTER TABLE sections
                    ADD CONSTRAINT ck_sections_unit_type_supported
                    CHECK (unit_type IN ('department', 'division', 'section', 'team'));
            END IF;
        END;
        $$;
        """
    )
    op.execute("ALTER TABLE sections DROP CONSTRAINT IF EXISTS sections_name_key")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_section_hierarchy()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            parent_unit_type text;
            parent_is_archived boolean;
        BEGIN
            PERFORM pg_advisory_xact_lock(1936028276);

            IF NEW.parent_id IS NOT NULL THEN
                SELECT unit_type, is_archived
                  INTO parent_unit_type, parent_is_archived
                  FROM sections
                 WHERE id = NEW.parent_id;

                IF parent_unit_type IS NULL THEN
                    RAISE EXCEPTION 'Parent section does not exist'
                        USING ERRCODE = '23503';
                END IF;
                IF parent_is_archived THEN
                    RAISE EXCEPTION 'Cannot assign an archived parent section'
                        USING ERRCODE = '23514';
                END IF;
                IF NOT (
                    (NEW.unit_type = 'division' AND parent_unit_type IN ('department', 'division'))
                    OR (NEW.unit_type = 'section' AND parent_unit_type IN ('department', 'division', 'section'))
                    OR (NEW.unit_type = 'team' AND parent_unit_type IN ('division', 'section', 'team'))
                ) THEN
                    RAISE EXCEPTION 'Invalid typed parent-child relationship'
                        USING ERRCODE = '23514';
                END IF;

                IF EXISTS (
                    WITH RECURSIVE ancestors(id, parent_id, visited) AS (
                        SELECT id, parent_id, ARRAY[id]
                        FROM sections
                        WHERE id = NEW.parent_id
                        UNION ALL
                        SELECT parent.id, parent.parent_id, ancestors.visited || parent.id
                        FROM sections parent
                        JOIN ancestors ON parent.id = ancestors.parent_id
                        WHERE NOT parent.id = ANY(ancestors.visited)
                    )
                    SELECT 1 FROM ancestors WHERE id = NEW.id
                ) THEN
                    RAISE EXCEPTION 'Section cannot be assigned beneath itself or its descendants'
                        USING ERRCODE = '23514';
                END IF;
            END IF;

            IF EXISTS (
                SELECT 1
                FROM sections child
                WHERE child.parent_id = NEW.id
                  AND NOT (
                      (child.unit_type = 'division' AND NEW.unit_type IN ('department', 'division'))
                      OR (child.unit_type = 'section' AND NEW.unit_type IN ('department', 'division', 'section'))
                      OR (child.unit_type = 'team' AND NEW.unit_type IN ('division', 'section', 'team'))
                  )
            ) THEN
                RAISE EXCEPTION 'Changing this unit type would invalidate a child relationship'
                    USING ERRCODE = '23514';
            END IF;

            IF NEW.is_archived AND EXISTS (
                SELECT 1 FROM sections child
                WHERE child.parent_id = NEW.id AND NOT child.is_archived
            ) THEN
                RAISE EXCEPTION 'Move or archive child units before archiving this unit'
                    USING ERRCODE = '23514';
            END IF;

            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_sections_hierarchy ON sections")
    op.execute(
        """
        CREATE TRIGGER trg_sections_hierarchy
        BEFORE INSERT OR UPDATE OF parent_id, unit_type, is_archived
        ON sections
        FOR EACH ROW
        EXECUTE FUNCTION enforce_section_hierarchy()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM sections
                GROUP BY name
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade: duplicate section names prevent restoring sections_name_key';
            END IF;
        END;
        $$;
        """
    )
    op.execute("ALTER TABLE sections ADD CONSTRAINT sections_name_key UNIQUE (name)")
    op.execute("DROP TRIGGER IF EXISTS trg_sections_hierarchy ON sections")
    op.execute("DROP FUNCTION IF EXISTS enforce_section_hierarchy()")
    op.execute(
        "ALTER TABLE sections DROP CONSTRAINT IF EXISTS ck_sections_unit_type_supported"
    )
