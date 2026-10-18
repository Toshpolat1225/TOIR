"""Add a dedicated permission for changing user active status."""

from alembic import op
from sqlalchemy import text

revision = "0009_user_active_permission"
down_revision = "0008_granular_permissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(text(
        "INSERT INTO permissions(code,module,action,label) "
        "VALUES ('users.set_active','users','update','Change user active status') "
        "ON CONFLICT (code) DO NOTHING"
    ))
    connection.execute(text(
        "INSERT INTO role_permissions(role,permission_code,granted) "
        "SELECT roles.role, 'users.set_active', roles.role = 'admin' "
        "FROM (VALUES ('admin'),('operator'),('master'),('management')) AS roles(role) "
        "ON CONFLICT (role,permission_code) DO NOTHING"
    ))


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission_code = 'users.set_active'")
    op.execute("DELETE FROM permissions WHERE code = 'users.set_active'")
