"""AUTH-01: TOIR keeps no passwords. The directory (AD) is the only way in.

Drops users.hashed_password; every user must be a directory account.

Revision ID: 0042_auth01_no_local_passwords
Revises: 0041_work_order_audit_duration
"""
from alembic import op
import sqlalchemy as sa

revision = "0042_auth01_no_local_passwords"
down_revision = "0041_work_order_audit_duration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # never silently delete the only way a local person could sign in (a DO block also works in offline --sql mode)
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM users WHERE auth_source <> 'ad' OR ad_username IS NULL) THEN
                RAISE EXCEPTION 'Some users are not directory accounts: convert or remove them first (this migration drops local passwords)';
            END IF;
        END $$;
        """
    )
    op.drop_constraint("ck_users_auth_credentials", "users", type_="check")
    op.drop_constraint("users_auth_source_check", "users", type_="check")
    op.drop_column("users", "hashed_password")
    op.alter_column("users", "auth_source", server_default=sa.text("'ad'"))
    op.create_check_constraint("users_auth_source_check", "users", "auth_source = 'ad'")
    op.create_check_constraint("ck_users_auth_credentials", "users", "ad_username IS NOT NULL")


def downgrade() -> None:
    op.drop_constraint("ck_users_auth_credentials", "users", type_="check")
    op.drop_constraint("users_auth_source_check", "users", type_="check")
    op.add_column("users", sa.Column("hashed_password", sa.Text(), nullable=True))
    op.alter_column("users", "auth_source", server_default=sa.text("'local'"))
    op.create_check_constraint("users_auth_source_check", "users", "auth_source IN ('local','ad')")
    op.create_check_constraint(
        "ck_users_auth_credentials",
        "users",
        "(auth_source = 'local' AND hashed_password IS NOT NULL"
        " AND ad_username IS NULL AND ad_object_guid IS NULL)"
        " OR (auth_source = 'ad' AND hashed_password IS NULL AND ad_username IS NOT NULL)",
    )
