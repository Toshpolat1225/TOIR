"""Add an optional unique GTK link to fixed assets."""

from alembic import op
import sqlalchemy as sa

revision = "0014_fixed_assets_gtk_id"
down_revision = "0013_gtk_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fixed_assets",
        sa.Column("gtk_id", sa.String(length=100), nullable=True),
    )
    op.create_unique_constraint(
        "uq_fixed_assets_gtk_id", "fixed_assets", ["gtk_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_fixed_assets_gtk_id", "fixed_assets", type_="unique")
    op.drop_column("fixed_assets", "gtk_id")
