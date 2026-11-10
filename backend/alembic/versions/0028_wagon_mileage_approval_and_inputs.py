"""Add opening approvals and explicit mileage calculation inputs.

Revision ID: 0028_mileage_approval_inputs
Revises: 0027_wagon_mileage_engine
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0028_mileage_approval_inputs"
down_revision = "0027_wagon_mileage_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_gtk_raw_snapshots_payload_hash",
        "gtk_raw_snapshots",
        type_="unique",
    )
    op.alter_column("gtk_raw_snapshots", "effective_at", nullable=True)
    op.create_index(
        "ix_gtk_raw_snapshots_payload_hash",
        "gtk_raw_snapshots",
        ["payload_hash"],
    )
    op.add_column(
        "gtk_raw_snapshots",
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_table(
        "gtk_membership_observations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("membership_id", sa.BigInteger(), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("change_type", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "change_type IN ('opened','closed')",
            name="ck_gtk_membership_observations_change_type",
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"], ["gtk_train_members.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["gtk_raw_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "membership_id",
            "snapshot_id",
            "change_type",
            name="uq_gtk_membership_observation",
        ),
    )

    op.alter_column("wialon_odometer_readings", "asset_id", nullable=True)
    op.alter_column("wialon_odometer_readings", "reading_at", nullable=True)
    op.add_column(
        "wialon_odometer_readings",
        sa.Column(
            "calculation_eligible",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "wialon_odometer_readings",
        sa.Column(
            "classification",
            sa.String(16),
            server_default=sa.text("'HELD'"),
            nullable=False,
        ),
    )
    op.add_column(
        "wialon_odometer_readings", sa.Column("measurement_key", sa.String(64))
    )
    op.create_check_constraint(
        "ck_wialon_odometer_classification",
        "wialon_odometer_readings",
        "classification IN ('CONFIRMED','ESTIMATED','HELD')",
    )
    op.create_unique_constraint(
        "uq_wialon_odometer_measurement_key",
        "wialon_odometer_readings",
        ["measurement_key"],
    )
    op.create_table(
        "wialon_raw_receipts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source_unit_id", sa.Text(), nullable=True),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reading_id", sa.BigInteger(), nullable=True),
        sa.Column("transport", sa.String(8), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "transport IN ('push','pull')",
            name="ck_wialon_raw_receipts_transport",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["fixed_assets.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["reading_id"],
            ["wialon_odometer_readings.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wialon_raw_receipts_received",
        "wialon_raw_receipts",
        ["received_at"],
    )
    op.create_index(
        "ix_wialon_raw_receipts_unit_received",
        "wialon_raw_receipts",
        ["source_unit_id", "received_at"],
    )

    op.add_column(
        "wagon_mileage_opening_balances",
        sa.Column(
            "approved_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "wagon_mileage_opening_balances",
        sa.Column(
            "supersedes_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "wagon_mileage_opening_balances.id", ondelete="RESTRICT"
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "wagon_mileage_opening_balances",
        sa.Column(
            "status",
            sa.String(16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
    )
    op.add_column(
        "wagon_mileage_opening_balances",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_wagon_mileage_opening_status",
        "wagon_mileage_opening_balances",
        "status IN ('pending','approved','rejected','superseded')",
    )
    op.create_check_constraint(
        "ck_wagon_mileage_opening_approval_audit",
        "wagon_mileage_opening_balances",
        "status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)",
    )
    op.create_index(
        "uq_wagon_mileage_opening_active_approved",
        "wagon_mileage_opening_balances",
        ["asset_id"],
        unique=True,
        postgresql_where=sa.text("status = 'approved'"),
    )

    op.add_column(
        "wagon_mileage_ledger",
        sa.Column(
            "classification",
            sa.String(16),
            server_default=sa.text("'HELD'"),
            nullable=False,
        ),
    )
    op.add_column(
        "wagon_mileage_ledger",
        sa.Column(
            "calculation_eligible",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_wagon_mileage_ledger_classification",
        "wagon_mileage_ledger",
        "classification IN ('CONFIRMED','ESTIMATED','HELD')",
    )

    op.create_table(
        "mileage_calculation_inputs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gtk_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("wialon_reading_id", sa.BigInteger(), nullable=True),
        sa.Column("opening_balance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("gtk_membership_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "(gtk_snapshot_id IS NOT NULL)::int + "
            "(wialon_reading_id IS NOT NULL)::int + "
            "(opening_balance_id IS NOT NULL)::int + "
            "(gtk_membership_id IS NOT NULL)::int = 1",
            name="ck_mileage_calculation_inputs_one_source",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["mileage_calculation_runs.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["gtk_snapshot_id"], ["gtk_raw_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["wialon_reading_id"],
            ["wialon_odometer_readings.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opening_balance_id"],
            ["wagon_mileage_opening_balances.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["gtk_membership_id"], ["gtk_train_members.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column, index_name in (
        ("gtk_snapshot_id", "uq_mileage_run_input_gtk_snapshot"),
        ("wialon_reading_id", "uq_mileage_run_input_wialon_reading"),
        ("opening_balance_id", "uq_mileage_run_input_opening_balance"),
        ("gtk_membership_id", "uq_mileage_run_input_gtk_membership"),
    ):
        op.create_index(
            index_name,
            "mileage_calculation_inputs",
            ["run_id", column],
            unique=True,
            postgresql_where=sa.text(f"{column} IS NOT NULL"),
        )


def downgrade() -> None:
    for index_name in (
        "uq_mileage_run_input_gtk_membership",
        "uq_mileage_run_input_opening_balance",
        "uq_mileage_run_input_wialon_reading",
        "uq_mileage_run_input_gtk_snapshot",
    ):
        op.drop_index(index_name, table_name="mileage_calculation_inputs")
    op.drop_table("mileage_calculation_inputs")

    op.drop_index(
        "ix_wialon_raw_receipts_unit_received",
        table_name="wialon_raw_receipts",
    )
    op.drop_index(
        "ix_wialon_raw_receipts_received",
        table_name="wialon_raw_receipts",
    )
    op.drop_table("wialon_raw_receipts")

    op.drop_constraint(
        "ck_wagon_mileage_ledger_classification",
        "wagon_mileage_ledger",
        type_="check",
    )
    op.drop_column("wagon_mileage_ledger", "calculation_eligible")
    op.drop_column("wagon_mileage_ledger", "classification")

    op.drop_index(
        "uq_wagon_mileage_opening_active_approved",
        table_name="wagon_mileage_opening_balances",
    )
    op.drop_constraint(
        "ck_wagon_mileage_opening_approval_audit",
        "wagon_mileage_opening_balances",
        type_="check",
    )
    op.drop_constraint(
        "ck_wagon_mileage_opening_status",
        "wagon_mileage_opening_balances",
        type_="check",
    )
    op.drop_column("wagon_mileage_opening_balances", "approved_at")
    op.drop_column("wagon_mileage_opening_balances", "status")
    op.drop_column("wagon_mileage_opening_balances", "supersedes_id")
    op.drop_column("wagon_mileage_opening_balances", "approved_by")

    op.drop_constraint(
        "ck_wialon_odometer_classification",
        "wialon_odometer_readings",
        type_="check",
    )
    op.drop_constraint(
        "uq_wialon_odometer_measurement_key",
        "wialon_odometer_readings",
        type_="unique",
    )
    op.drop_column("wialon_odometer_readings", "measurement_key")
    op.drop_column("wialon_odometer_readings", "classification")
    op.drop_column("wialon_odometer_readings", "calculation_eligible")
    op.alter_column("wialon_odometer_readings", "reading_at", nullable=False)
    op.alter_column("wialon_odometer_readings", "asset_id", nullable=False)

    op.drop_table("gtk_membership_observations")
    op.drop_column("gtk_raw_snapshots", "observed_at")
    op.drop_index("ix_gtk_raw_snapshots_payload_hash", table_name="gtk_raw_snapshots")
    op.alter_column("gtk_raw_snapshots", "effective_at", nullable=False)
    op.create_unique_constraint(
        "uq_gtk_raw_snapshots_payload_hash",
        "gtk_raw_snapshots",
        ["payload_hash"],
    )
