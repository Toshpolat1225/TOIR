"""Attribute locomotive mileage to GTK wagons."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015_gtk_wagon_mileage"
down_revision = "0014_fixed_assets_gtk_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "mileage_history_source_check", "mileage_history", type_="check"
    )
    op.create_check_constraint(
        "mileage_history_source_check",
        "mileage_history",
        "source IN ('wialon','manual','gtk')",
    )

    op.create_table(
        "gtk_wagon_mileage_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("wagon_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("loco_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("train_gtk_id", sa.Integer(), nullable=False),
        sa.Column("period_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("km", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["wagon_asset_id"],
            ["fixed_assets.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_gtk_wagon_mileage_log_wagon_period",
        "gtk_wagon_mileage_log",
        ["wagon_asset_id", "period_to"],
    )
    op.create_index(
        "ix_gtk_wagon_mileage_log_train",
        "gtk_wagon_mileage_log",
        ["train_gtk_id"],
    )

    op.create_table(
        "gtk_locomotive_mileage_checkpoints",
        sa.Column("locomotive_gtk_id", sa.Integer(), nullable=False),
        sa.Column("locomotive_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mileage", sa.Numeric(12, 2), nullable=False),
        sa.Column("checkpoint_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["locomotive_asset_id"],
            ["fixed_assets.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("locomotive_gtk_id"),
        sa.UniqueConstraint("locomotive_asset_id"),
    )


def downgrade() -> None:
    op.drop_table("gtk_locomotive_mileage_checkpoints")
    op.drop_index(
        "ix_gtk_wagon_mileage_log_train", table_name="gtk_wagon_mileage_log"
    )
    op.drop_index(
        "ix_gtk_wagon_mileage_log_wagon_period",
        table_name="gtk_wagon_mileage_log",
    )
    op.drop_table("gtk_wagon_mileage_log")

    op.drop_constraint(
        "mileage_history_source_check", "mileage_history", type_="check"
    )
    op.create_check_constraint(
        "mileage_history_source_check",
        "mileage_history",
        "source IN ('wialon','manual')",
    )
