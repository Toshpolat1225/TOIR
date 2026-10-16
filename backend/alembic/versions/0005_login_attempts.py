"""Persist login throttling state across backend processes.

Revision ID: 0005_login_attempts
Revises: 0004_realtime_scopes
Create Date: 2026-10-16
"""

from alembic import op

revision = "0005_login_attempts"
down_revision = "0004_realtime_scopes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE login_attempts (
            id bigserial PRIMARY KEY,
            key_hash varchar(64) NOT NULL,
            failed_at timestamptz NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_login_attempts_key_failed "
        "ON login_attempts(key_hash, failed_at)"
    )
    op.execute(
        "CREATE INDEX ix_login_attempts_failed_at ON login_attempts(failed_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE login_attempts")
