"""Remove unused source-side locomotive mileage checkpoints."""

from alembic import op
import sqlalchemy as sa

revision = "0016_gtk_mirror_cleanup"
down_revision = "0015_gtk_wagon_mileage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("gtk_locomotives", "checkpoint_at")
    op.drop_column("gtk_locomotives", "checkpoint_mileage")


def downgrade() -> None:
    op.add_column(
        "gtk_locomotives",
        sa.Column("checkpoint_mileage", sa.Numeric(16, 2), nullable=True),
    )
    op.add_column(
        "gtk_locomotives",
        sa.Column("checkpoint_at", sa.DateTime(timezone=True), nullable=True),
    )
