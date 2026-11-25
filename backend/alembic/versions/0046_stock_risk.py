"""Spare-part stock risk: 1C stock balances, supplier lead times, purchase orders.

Additive only: three new tables, no change to existing ones. Permissions reuse analytics.view / inventory.*.

Revision ID: 0046_stock_risk
Revises: 0045_repair_norm_groups
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0046_stock_risk"
down_revision = "0045_repair_norm_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_balances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("nomenclature_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("nomenclature.id", ondelete="CASCADE"), nullable=False),
        sa.Column("warehouse", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("qty", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit", sa.Text()),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default=sa.text("'1c_import'")),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("qty >= 0", name="ck_stock_balances_qty"),
        sa.CheckConstraint("source IN ('1c_import','manual','demo')", name="ck_stock_balances_source"),
        sa.UniqueConstraint("nomenclature_id", "warehouse", "as_of", name="uq_stock_balances_key"),
    )
    op.create_index("ix_stock_balances_nomenclature", "stock_balances", ["nomenclature_id", "as_of"])
    op.create_table(
        "supplier_terms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("nomenclature_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("nomenclature.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("supplier", sa.Text()),
        sa.Column("lead_time_days", sa.Integer(), nullable=False),
        sa.Column("min_order_qty", sa.Numeric(14, 3)),
        sa.Column("safety_days", sa.Integer(), nullable=False, server_default=sa.text("14")),
        sa.Column("note", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("lead_time_days > 0", name="ck_supplier_terms_lead"),
        sa.CheckConstraint("safety_days >= 0", name="ck_supplier_terms_safety"),
        sa.CheckConstraint("min_order_qty IS NULL OR min_order_qty > 0", name="ck_supplier_terms_moq"),
    )
    op.create_table(
        "purchase_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("nomenclature_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("nomenclature.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doc_no", sa.Text()),
        sa.Column("supplier", sa.Text()),
        sa.Column("qty", sa.Numeric(14, 3), nullable=False),
        sa.Column("qty_received", sa.Numeric(14, 3), nullable=False, server_default=sa.text("0")),
        sa.Column("ordered_on", sa.Date()),
        sa.Column("expected_on", sa.Date()),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'ordered'")),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("qty > 0", name="ck_purchase_orders_qty"),
        sa.CheckConstraint("qty_received >= 0", name="ck_purchase_orders_received"),
        sa.CheckConstraint("status IN ('ordered','in_transit','partial','received','cancelled')", name="ck_purchase_orders_status"),
    )
    op.create_index("ix_purchase_orders_nomenclature", "purchase_orders", ["nomenclature_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_purchase_orders_nomenclature", table_name="purchase_orders")
    op.drop_table("purchase_orders")
    op.drop_table("supplier_terms")
    op.drop_index("ix_stock_balances_nomenclature", table_name="stock_balances")
    op.drop_table("stock_balances")
