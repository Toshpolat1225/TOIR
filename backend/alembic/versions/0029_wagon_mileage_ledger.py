"""Complete idempotent wagon mileage ledger inputs and constraints.

Revision ID: 0029_wagon_mileage_ledger
Revises: 0028_mileage_approval_inputs
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0029_wagon_mileage_ledger"
down_revision = "0028_mileage_approval_inputs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wialon_odometer_readings",
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE wialon_odometer_readings SET observed_at = reading_at "
        "WHERE observed_at IS NULL"
    )
    op.add_column(
        "wialon_odometer_readings",
        sa.Column(
            "resolution_km",
            sa.Numeric(8, 3),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.add_column(
        "wialon_odometer_readings",
        sa.Column(
            "source",
            sa.String(8),
            server_default=sa.text("'pull'"),
            nullable=False,
        ),
    )
    op.add_column(
        "wialon_odometer_readings",
        sa.Column("external_id", sa.String(128), nullable=True),
    )
    op.create_check_constraint(
        "ck_wialon_odometer_source",
        "wialon_odometer_readings",
        "source IN ('push','pull')",
    )
    op.create_index(
        "ix_wialon_odometer_observed_at",
        "wialon_odometer_readings",
        ["observed_at"],
    )

    op.drop_constraint(
        "ck_wagon_mileage_ledger_nonnegative",
        "wagon_mileage_ledger",
        type_="check",
    )
    op.drop_constraint(
        "ck_wagon_mileage_ledger_period",
        "wagon_mileage_ledger",
        type_="check",
    )
    op.alter_column(
        "wagon_mileage_ledger",
        "km",
        new_column_name="distance_km",
    )
    op.create_check_constraint(
        "ck_wagon_mileage_ledger_distance_nonnegative",
        "wagon_mileage_ledger",
        "distance_km >= 0",
    )
    op.create_check_constraint(
        "ck_wagon_mileage_ledger_period",
        "wagon_mileage_ledger",
        "period_to > period_from",
    )
    op.add_column(
        "wagon_mileage_ledger",
        sa.Column(
            "algorithm_version",
            sa.String(32),
            server_default=sa.text("'wagon-mileage-v1'"),
            nullable=False,
        ),
    )
    op.add_column(
        "wagon_mileage_ledger",
        sa.Column(
            "input_hash",
            sa.String(64),
            server_default=sa.text("'legacy'"),
            nullable=False,
        ),
    )
    op.add_column(
        "wagon_mileage_ledger",
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_wagon_mileage_ledger_supersedes",
        "wagon_mileage_ledger",
        "wagon_mileage_ledger",
        ["supersedes_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_wagon_mileage_ledger_train",
        "wagon_mileage_ledger",
        "gtk_trains",
        ["train_gtk_id"],
        ["gtk_id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "ck_wagon_idle_period",
        "wagon_idle_periods",
        type_="check",
    )
    op.create_check_constraint(
        "ck_wagon_idle_period",
        "wagon_idle_periods",
        "period_to > period_from",
    )
    op.add_column(
        "wagon_idle_periods",
        sa.Column(
            "distance_km",
            sa.Numeric(12, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "wagon_idle_periods",
        sa.Column("idempotency_key", sa.String(128), nullable=True),
    )
    op.execute(
        "UPDATE wagon_idle_periods SET idempotency_key = "
        "md5(id::text || period_from::text || period_to::text) "
        "WHERE idempotency_key IS NULL"
    )
    op.alter_column(
        "wagon_idle_periods",
        "idempotency_key",
        nullable=False,
    )
    op.create_check_constraint(
        "ck_wagon_idle_distance_zero",
        "wagon_idle_periods",
        "distance_km = 0",
    )
    op.create_unique_constraint(
        "uq_wagon_idle_period_idempotency",
        "wagon_idle_periods",
        ["idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_wagon_idle_period_idempotency",
        "wagon_idle_periods",
        type_="unique",
    )
    op.drop_constraint(
        "ck_wagon_idle_distance_zero",
        "wagon_idle_periods",
        type_="check",
    )
    op.drop_column("wagon_idle_periods", "idempotency_key")
    op.drop_column("wagon_idle_periods", "distance_km")
    op.drop_constraint(
        "ck_wagon_idle_period",
        "wagon_idle_periods",
        type_="check",
    )
    op.create_check_constraint(
        "ck_wagon_idle_period",
        "wagon_idle_periods",
        "period_to >= period_from",
    )
    op.drop_constraint(
        "fk_wagon_mileage_ledger_train",
        "wagon_mileage_ledger",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_wagon_mileage_ledger_supersedes",
        "wagon_mileage_ledger",
        type_="foreignkey",
    )
    op.drop_column("wagon_mileage_ledger", "supersedes_id")
    op.drop_column("wagon_mileage_ledger", "input_hash")
    op.drop_column("wagon_mileage_ledger", "algorithm_version")
    op.drop_constraint(
        "ck_wagon_mileage_ledger_period",
        "wagon_mileage_ledger",
        type_="check",
    )
    op.drop_constraint(
        "ck_wagon_mileage_ledger_distance_nonnegative",
        "wagon_mileage_ledger",
        type_="check",
    )
    op.alter_column(
        "wagon_mileage_ledger",
        "distance_km",
        new_column_name="km",
    )
    op.create_check_constraint(
        "ck_wagon_mileage_ledger_nonnegative",
        "wagon_mileage_ledger",
        "km >= 0",
    )
    op.create_check_constraint(
        "ck_wagon_mileage_ledger_period",
        "wagon_mileage_ledger",
        "period_to >= period_from",
    )
    op.drop_index(
        "ix_wialon_odometer_observed_at",
        table_name="wialon_odometer_readings",
    )
    op.drop_constraint(
        "ck_wialon_odometer_source",
        "wialon_odometer_readings",
        type_="check",
    )
    op.drop_column("wialon_odometer_readings", "external_id")
    op.drop_column("wialon_odometer_readings", "source")
    op.drop_column("wialon_odometer_readings", "resolution_km")
    op.drop_column("wialon_odometer_readings", "observed_at")
