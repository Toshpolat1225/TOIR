"""Include section scopes in PostgreSQL realtime notifications.

Revision ID: 0004_realtime_scopes
Revises: 0003_analytics
Create Date: 2026-10-16
"""

from alembic import op

revision = "0004_realtime_scopes"
down_revision = "0003_analytics"
branch_labels = None
depends_on = None


_SCOPED_NOTIFY_FUNCTION = """
CREATE OR REPLACE FUNCTION notify_change() RETURNS trigger AS $$
DECLARE
    changed_id uuid;
    scopes uuid[] := ARRAY[]::uuid[];
BEGIN
    IF TG_OP <> 'INSERT' THEN
        changed_id := OLD.id;
        IF OLD.section_id IS NOT NULL THEN
            scopes := array_append(scopes, OLD.section_id);
        END IF;
    END IF;
    IF TG_OP <> 'DELETE' THEN
        changed_id := NEW.id;
        IF NEW.section_id IS NOT NULL
           AND NOT (NEW.section_id = ANY(scopes)) THEN
            scopes := array_append(scopes, NEW.section_id);
        END IF;
    END IF;
    PERFORM pg_notify(
        'toir_changes',
        json_build_object(
            'table', TG_TABLE_NAME,
            'op', TG_OP,
            'id', changed_id,
            'section_ids', scopes
        )::text
    );
    RETURN NULL;
END;
$$ LANGUAGE plpgsql
"""


def upgrade() -> None:
    op.execute(_SCOPED_NOTIFY_FUNCTION)


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION notify_change() RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify(
                'toir_changes',
                json_build_object(
                    'table', TG_TABLE_NAME,
                    'op', TG_OP,
                    'id', COALESCE(NEW.id, OLD.id)
                )::text
            );
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
        """
    )
