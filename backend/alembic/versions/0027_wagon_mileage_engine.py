"""Add auditable wagon mileage calculation foundations.

Revision ID: 0027_wagon_mileage_engine
Revises: 0026_audit_logs
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0027_wagon_mileage_engine"
down_revision = "0026_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gtk_raw_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("sync_run_id", sa.BigInteger(), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("is_complete", sa.Boolean(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["sync_run_id"], ["gtk_sync_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payload_hash", name="uq_gtk_raw_snapshots_payload_hash"),
    )
    op.create_index("ix_gtk_raw_snapshots_effective_received", "gtk_raw_snapshots", ["effective_at", "received_at"])

    op.create_table(
        "wialon_odometer_readings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_unit_id", sa.Text(), nullable=False),
        sa.Column("odometer_km", sa.Numeric(16, 2), nullable=False),
        sa.Column("reading_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("odometer_km >= 0", name="ck_wialon_odometer_readings_nonnegative"),
        sa.ForeignKeyConstraint(["asset_id"], ["fixed_assets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payload_hash", name="uq_wialon_odometer_readings_payload_hash"),
    )
    op.create_index("ix_wialon_odometer_asset_time", "wialon_odometer_readings", ["asset_id", "reading_at"])

    op.create_table(
        "wagon_mileage_opening_balances",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mileage_km", sa.Numeric(12, 2), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("mileage_km >= 0", name="ck_wagon_mileage_opening_nonnegative"),
        sa.ForeignKeyConstraint(["asset_id"], ["fixed_assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wagon_mileage_opening_asset_effective", "wagon_mileage_opening_balances", ["asset_id", "effective_at"])

    op.create_table(
        "mileage_calculation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("algorithm_version", sa.String(32), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'running'"), nullable=False),
        sa.Column("input_watermark", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('running','completed','partial','failed')", name="ck_mileage_calculation_runs_status"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["gtk_raw_snapshots.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mileage_calculation_runs_started", "mileage_calculation_runs", ["started_at"])

    op.create_table(
        "wagon_mileage_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("wagon_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("locomotive_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("train_gtk_id", sa.Integer(), nullable=True),
        sa.Column("period_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("km", sa.Numeric(12, 2), nullable=False),
        sa.Column("estimated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'active'"), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("calculation_details", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("km >= 0", name="ck_wagon_mileage_ledger_nonnegative"),
        sa.CheckConstraint("period_to >= period_from", name="ck_wagon_mileage_ledger_period"),
        sa.CheckConstraint("status IN ('active','superseded','rejected')", name="ck_wagon_mileage_ledger_status"),
        sa.ForeignKeyConstraint(["run_id"], ["mileage_calculation_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["wagon_asset_id"], ["fixed_assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["locomotive_asset_id"], ["fixed_assets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_wagon_mileage_ledger_idempotency"),
    )
    op.create_index("ix_wagon_mileage_ledger_asset_period", "wagon_mileage_ledger", ["wagon_asset_id", "period_from", "period_to"])
    op.create_index("ix_wagon_mileage_ledger_run", "wagon_mileage_ledger", ["run_id"])

    op.create_table(
        "wagon_idle_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("wagon_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_gtk_id", sa.BigInteger(), nullable=True),
        sa.Column("period_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("period_to >= period_from", name="ck_wagon_idle_period"),
        sa.CheckConstraint("status IN ('confirmed','unknown_activity','estimated')", name="ck_wagon_idle_status"),
        sa.ForeignKeyConstraint(["wagon_asset_id"], ["fixed_assets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_wagon_idle_asset_period", "wagon_idle_periods", ["wagon_asset_id", "period_from"])


def downgrade() -> None:
    op.drop_index("ix_wagon_idle_asset_period", table_name="wagon_idle_periods")
    op.drop_table("wagon_idle_periods")
    op.drop_index("ix_wagon_mileage_ledger_run", table_name="wagon_mileage_ledger")
    op.drop_index("ix_wagon_mileage_ledger_asset_period", table_name="wagon_mileage_ledger")
    op.drop_table("wagon_mileage_ledger")
    op.drop_index("ix_mileage_calculation_runs_started", table_name="mileage_calculation_runs")
    op.drop_table("mileage_calculation_runs")
    op.drop_index("ix_wagon_mileage_opening_asset_effective", table_name="wagon_mileage_opening_balances")
    op.drop_table("wagon_mileage_opening_balances")
    op.drop_index("ix_wialon_odometer_asset_time", table_name="wialon_odometer_readings")
    op.drop_table("wialon_odometer_readings")
    op.drop_index("ix_gtk_raw_snapshots_effective_received", table_name="gtk_raw_snapshots")
    op.drop_table("gtk_raw_snapshots")
