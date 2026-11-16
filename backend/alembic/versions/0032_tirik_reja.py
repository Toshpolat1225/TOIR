"""Tirik reja: baselines, ranks, lead time, tolerance, blocked/covered/waived plans, decisions, disruptions.

Additive only. Existing rows keep their meaning; the new interval columns get the proposal's defaults
for the standard ТО/ТР/СР/КР codes (the `test` interval and unknown codes stay unranked and independent).

Revision ID: 0032_tirik_reja
Revises: 0031_plan_manual_date
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0032_tirik_reja"
down_revision = "0031_plan_manual_date"
branch_labels = None
depends_on = None

# code, rank, lead_days, tolerance_pct
STANDARD_INTERVALS = [
    ("ТО-1", 1, 7, 10),
    ("ТО-2", 2, 14, 10),
    ("ТО-3", 3, 21, 10),
    ("ТР-1", 4, 45, 5),
    ("ТР-2", 5, 60, 5),
    ("ТР-3", 6, 90, 5),
    ("СР", 7, 120, 0),
    ("КР", 8, 180, 0),
]
OLD_STATUSES = "status IN ('scheduled','in_progress','completed','cancelled')"
NEW_STATUSES = "status IN ('scheduled','in_progress','completed','cancelled','blocked','covered','waived')"


def upgrade() -> None:
    # ── maintenance_intervals ────────────────────────────────────────────────
    op.add_column("maintenance_intervals", sa.Column("rank", sa.Integer(), nullable=True))
    op.add_column("maintenance_intervals", sa.Column("interval_hours", sa.Numeric(12, 2), nullable=True))
    op.add_column(
        "maintenance_intervals",
        sa.Column("tolerance_pct", sa.Numeric(5, 2), server_default=sa.text("10"), nullable=False),
    )
    op.add_column(
        "maintenance_intervals",
        sa.Column("lead_days", sa.Integer(), server_default=sa.text("7"), nullable=False),
    )
    op.create_check_constraint("ck_interval_tolerance_range", "maintenance_intervals", "tolerance_pct >= 0 AND tolerance_pct <= 100")
    op.create_check_constraint("ck_interval_lead_days_range", "maintenance_intervals", "lead_days >= 0 AND lead_days <= 1000")
    op.drop_constraint("ck_interval_defined", "maintenance_intervals", type_="check")
    op.create_check_constraint(
        "ck_interval_defined",
        "maintenance_intervals",
        "interval_km IS NOT NULL OR interval_days IS NOT NULL OR interval_hours IS NOT NULL",
    )
    bind = op.get_bind()
    for code, rank, lead_days, tolerance in STANDARD_INTERVALS:
        bind.execute(
            sa.text(
                "UPDATE maintenance_intervals SET rank = :rank, lead_days = :lead, tolerance_pct = :tol WHERE code = :code"
            ),
            {"rank": rank, "lead": lead_days, "tol": tolerance, "code": code},
        )

    # ── maintenance_plan ─────────────────────────────────────────────────────
    op.add_column("maintenance_plan", sa.Column("blocked_reason", sa.Text(), nullable=True))
    op.add_column("maintenance_plan", sa.Column("blocked_until", sa.Date(), nullable=True))
    op.add_column("maintenance_plan", sa.Column("blocked_note", sa.Text(), nullable=True))
    op.add_column(
        "maintenance_plan",
        sa.Column("deferral_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "maintenance_plan",
        sa.Column(
            "covered_by_plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("maintenance_plan.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("maintenance_plan", sa.Column("completed_km", sa.Numeric(14, 2), nullable=True))
    op.add_column("maintenance_plan", sa.Column("completed_hours", sa.Numeric(14, 3), nullable=True))
    op.drop_constraint("maintenance_plan_status_check", "maintenance_plan", type_="check")
    op.create_check_constraint("maintenance_plan_status_check", "maintenance_plan", NEW_STATUSES)
    op.create_check_constraint(
        "ck_maintenance_plan_blocked_consistency",
        "maintenance_plan",
        "(status = 'blocked') = (blocked_reason IS NOT NULL)",
    )
    op.create_check_constraint("ck_maintenance_plan_deferral_count", "maintenance_plan", "deferral_count >= 0")

    # ── asset_maintenance_baseline ───────────────────────────────────────────
    op.create_table(
        "asset_maintenance_baseline",
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("interval_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("maintenance_intervals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("done_at", sa.Date(), nullable=True),
        sa.Column("km", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("hours", sa.Numeric(14, 3), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("work_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("asset_id", "interval_id", name="asset_maintenance_baseline_pkey"),
        sa.CheckConstraint("hours IS NULL OR hours >= 0", name="ck_baseline_hours_nonnegative"),
        sa.CheckConstraint("source IN ('provisional','import','completed','manual','waived')", name="ck_baseline_source"),
    )

    # ── maintenance_decision ─────────────────────────────────────────────────
    op.create_table(
        "maintenance_decision",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("maintenance_plan.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("from_date", sa.Date(), nullable=True),
        sa.Column("to_date", sa.Date(), nullable=True),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind IN ('reschedule','block','unblock','waive','cover','release')", name="ck_decision_kind"),
        sa.CheckConstraint("note IS NULL OR char_length(note) <= 500", name="ck_decision_note_len"),
    )
    op.create_index("ix_decision_plan_time", "maintenance_decision", ["plan_id", "created_at"])

    # ── maintenance_disruption ───────────────────────────────────────────────
    op.create_table(
        "maintenance_disruption",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=True),
        sa.Column("section_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sections.id", ondelete="SET NULL"), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'open'"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('parts','no_bay','no_crew','unit_unavailable','accident','unplanned_repair','sensor_failure','weather','other')",
            name="ck_disruption_kind",
        ),
        sa.CheckConstraint("scope IN ('asset','section','all')", name="ck_disruption_scope"),
        sa.CheckConstraint("status IN ('open','closed')", name="ck_disruption_status"),
        sa.CheckConstraint(
            "(scope <> 'asset' OR asset_id IS NOT NULL) AND (scope <> 'section' OR section_id IS NOT NULL)",
            name="ck_disruption_scope_target",
        ),
        sa.CheckConstraint("ends_on IS NULL OR ends_on >= starts_on", name="ck_disruption_dates"),
        sa.CheckConstraint("note IS NULL OR char_length(note) <= 500", name="ck_disruption_note_len"),
    )
    op.create_index("ix_disruption_status_dates", "maintenance_disruption", ["status", "starts_on", "ends_on"])

    # ── asset_meter_daily ────────────────────────────────────────────────────
    # Which disruption blocked a plan (so that closing the disruption can release exactly those plans).
    op.add_column(
        "maintenance_plan",
        sa.Column(
            "blocked_by_disruption_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("maintenance_disruption.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.create_table(
        "asset_meter_daily",
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fixed_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("km", sa.Numeric(14, 2), nullable=True),
        sa.Column("hours", sa.Numeric(14, 3), nullable=True),
        sa.PrimaryKeyConstraint("asset_id", "day", name="asset_meter_daily_pkey"),
    )


def downgrade() -> None:
    op.drop_table("asset_meter_daily")
    op.drop_column("maintenance_plan", "blocked_by_disruption_id")
    op.drop_index("ix_disruption_status_dates", table_name="maintenance_disruption")
    op.drop_table("maintenance_disruption")
    op.drop_index("ix_decision_plan_time", table_name="maintenance_decision")
    op.drop_table("maintenance_decision")
    op.drop_table("asset_maintenance_baseline")

    # The new plan states cannot exist in the old schema: put them back to the closest old meaning.
    op.execute("UPDATE maintenance_plan SET status = 'scheduled', blocked_reason = NULL WHERE status = 'blocked'")
    op.execute("UPDATE maintenance_plan SET status = 'completed' WHERE status IN ('covered','waived')")
    op.drop_constraint("ck_maintenance_plan_deferral_count", "maintenance_plan", type_="check")
    op.drop_constraint("ck_maintenance_plan_blocked_consistency", "maintenance_plan", type_="check")
    op.drop_constraint("maintenance_plan_status_check", "maintenance_plan", type_="check")
    op.create_check_constraint("maintenance_plan_status_check", "maintenance_plan", OLD_STATUSES)
    for column in ("completed_hours", "completed_km", "covered_by_plan_id", "deferral_count", "blocked_note", "blocked_until", "blocked_reason"):
        op.drop_column("maintenance_plan", column)

    op.drop_constraint("ck_interval_defined", "maintenance_intervals", type_="check")
    op.create_check_constraint("ck_interval_defined", "maintenance_intervals", "interval_km IS NOT NULL OR interval_days IS NOT NULL")
    op.drop_constraint("ck_interval_lead_days_range", "maintenance_intervals", type_="check")
    op.drop_constraint("ck_interval_tolerance_range", "maintenance_intervals", type_="check")
    for column in ("lead_days", "tolerance_pct", "interval_hours", "rank"):
        op.drop_column("maintenance_intervals", column)
