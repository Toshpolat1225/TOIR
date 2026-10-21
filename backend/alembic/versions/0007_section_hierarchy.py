"""Add hierarchical parent metadata to sections.

Revision ID: 0007_section_hierarchy
Revises: 0006_localization
"""

from alembic import op

revision = "0007_section_hierarchy"
down_revision = "0006_localization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sections ADD COLUMN IF NOT EXISTS parent_id uuid NULL")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'sections_parent_id_fkey'
                  AND conrelid = 'sections'::regclass
            ) THEN
                ALTER TABLE sections
                    ADD CONSTRAINT sections_parent_id_fkey
                    FOREIGN KEY (parent_id) REFERENCES sections(id)
                    ON DELETE SET NULL;
            END IF;
        END;
        $$;
        """
    )
    op.execute("ALTER TABLE sections ADD COLUMN IF NOT EXISTS unit_type text NOT NULL DEFAULT 'section'")
    op.execute("ALTER TABLE sections ADD COLUMN IF NOT EXISTS code text NULL")
    op.execute("ALTER TABLE sections ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true")
    op.execute("ALTER TABLE sections ADD COLUMN IF NOT EXISTS is_archived boolean NOT NULL DEFAULT false")
    op.execute("ALTER TABLE sections ADD COLUMN IF NOT EXISTS sort_order integer NOT NULL DEFAULT 0")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sections_parent ON sections(parent_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sections_type ON sections(unit_type)")
    op.execute("UPDATE sections SET unit_type = 'section' WHERE unit_type IS NULL OR unit_type = ''")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_sections_type")
    op.execute("DROP INDEX IF EXISTS ix_sections_parent")
    op.execute("ALTER TABLE sections DROP CONSTRAINT IF EXISTS sections_parent_id_fkey")
    for column in ("sort_order", "is_archived", "is_active", "code", "unit_type", "parent_id"):
        op.execute(f"ALTER TABLE sections DROP COLUMN IF EXISTS {column}")
