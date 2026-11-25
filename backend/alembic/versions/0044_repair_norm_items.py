"""Repair consumption norms per equipment type/model and repair kind (not tied to a department).

Additive only: one new table. Permissions reuse the existing inventory.* codes.

Revision ID: 0044_repair_norm_items
Revises: 0043_data_migration_journal
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0044_repair_norm_items"
down_revision = "0043_data_migration_journal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repair_norm_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("work_type_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("work_types.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_type", sa.Text(), sa.ForeignKey("fixed_asset_types.code", onupdate="CASCADE", ondelete="RESTRICT"), nullable=False),
        sa.Column("asset_model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("asset_models.id", ondelete="SET NULL")),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("section", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text()),
        sa.Column("quantity", sa.Numeric(14, 3)),
        sa.Column("quantity_text", sa.Text(), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repair_norm_items.id", ondelete="CASCADE")),
        sa.Column("note", sa.Text()),
        sa.Column("source_file", sa.Text()),
        sa.Column("source_sheet", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.CheckConstraint("section IN ('materials','spare_parts')", name="ck_repair_norm_items_section"),
        sa.CheckConstraint("quantity IS NULL OR quantity >= 0", name="ck_repair_norm_items_quantity"),
    )
    op.create_index("ix_repair_norm_items_set", "repair_norm_items", ["work_type_id", "asset_type", "asset_model_id", "seq"])
    op.create_index("ix_repair_norm_items_parent", "repair_norm_items", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_repair_norm_items_parent", table_name="repair_norm_items")
    op.drop_index("ix_repair_norm_items_set", table_name="repair_norm_items")
    op.drop_table("repair_norm_items")
