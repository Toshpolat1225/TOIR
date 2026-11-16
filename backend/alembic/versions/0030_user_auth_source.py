"""Users: login source (local password or Active Directory).

Revision ID: 0030_user_auth_source
Revises: 0029_wagon_mileage_ledger
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0030_user_auth_source"
down_revision = "0029_wagon_mileage_ledger"
branch_labels = None
depends_on = None

# A valid bcrypt hash of a random, discarded string: nobody can log in with it.
UNUSABLE_LOCAL_HASH = "$2b$12$u/2mXTClZazUzJHXRRv/xuSDhBrkGhcTypLG060HcQFhfSy0ICz7a"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "auth_source",
            sa.Text(),
            server_default=sa.text("'local'"),
            nullable=False,
        ),
    )
    op.add_column("users", sa.Column("ad_username", postgresql.CITEXT(), nullable=True))
    op.add_column(
        "users", sa.Column("ad_object_guid", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.alter_column("users", "hashed_password", existing_type=sa.Text(), nullable=True)
    op.create_unique_constraint("users_ad_username_key", "users", ["ad_username"])
    op.create_unique_constraint("users_ad_object_guid_key", "users", ["ad_object_guid"])
    op.create_check_constraint(
        "users_auth_source_check", "users", "auth_source IN ('local','ad')"
    )
    op.create_check_constraint(
        "ck_users_auth_credentials",
        "users",
        "(auth_source = 'local' AND hashed_password IS NOT NULL"
        " AND ad_username IS NULL AND ad_object_guid IS NULL)"
        " OR (auth_source = 'ad' AND hashed_password IS NULL AND ad_username IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_auth_credentials", "users", type_="check")
    op.drop_constraint("users_auth_source_check", "users", type_="check")
    op.drop_constraint("users_ad_object_guid_key", "users", type_="unique")
    op.drop_constraint("users_ad_username_key", "users", type_="unique")
    # Directory accounts have no local password. Keep their rows, but they
    # cannot log in: unusable hash and deactivated.
    op.execute(
        sa.text(
            "UPDATE users SET hashed_password = :hash, is_active = false "
            "WHERE hashed_password IS NULL"
        ).bindparams(hash=UNUSABLE_LOCAL_HASH)
    )
    op.alter_column("users", "hashed_password", existing_type=sa.Text(), nullable=False)
    op.drop_column("users", "ad_object_guid")
    op.drop_column("users", "ad_username")
    op.drop_column("users", "auth_source")
