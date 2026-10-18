"""Add database-backed role permissions and immutable audit records.

Revision ID: 0008_granular_permissions
Revises: 0007_asset_catalog_management
"""

from alembic import op

revision = "0008_granular_permissions"
down_revision = "0007_asset_catalog_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE permissions (
            code text PRIMARY KEY,
            module text NOT NULL,
            action text NOT NULL,
            label text NOT NULL,
            CONSTRAINT ck_permissions_action CHECK (action IN ('view','create','update','delete','export','approve','manage_permissions','manage_users','manage_reference_data'))
        )
    """)
    op.execute("""
        CREATE TABLE role_permissions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            role text NOT NULL CONSTRAINT ck_role_permissions_role CHECK (role IN ('admin','operator','master','management')),
            permission_code text NOT NULL REFERENCES permissions(code) ON DELETE CASCADE,
            granted boolean NOT NULL DEFAULT false,
            CONSTRAINT uq_role_permissions_role_code UNIQUE (role, permission_code)
        )
    """)
    op.execute("CREATE INDEX ix_role_permissions_role ON role_permissions(role)")
    op.execute("""
        CREATE TABLE permission_audit (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
            target_role text NOT NULL CONSTRAINT ck_permission_audit_role CHECK (target_role IN ('admin','operator','master','management')),
            permission_code text NOT NULL,
            previous_granted boolean NOT NULL,
            new_granted boolean NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_permission_audit_created_at ON permission_audit(created_at)")
    from app.core.permissions import PERMISSIONS, ROLE_DEFAULTS
    from sqlalchemy.sql import text
    connection = op.get_bind()
    for code, (module, action, label) in PERMISSIONS.items():
        connection.execute(text("INSERT INTO permissions(code,module,action,label) VALUES (:code,:module,:action,:label)"), {"code": code, "module": module, "action": action, "label": label})
        for role, grants in ROLE_DEFAULTS.items():
            connection.execute(text("INSERT INTO role_permissions(role,permission_code,granted) VALUES (:role,:code,:granted)"), {"role": role, "code": code, "granted": code in grants})


def downgrade() -> None:
    op.execute("DROP TABLE permission_audit")
    op.execute("DROP TABLE role_permissions")
    op.execute("DROP TABLE permissions")
