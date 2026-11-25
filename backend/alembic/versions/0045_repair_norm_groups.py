"""Repair norms for locomotives: a series group (ТЭМ2+ТЭМ18+ТЭМ18ДМ), assembly sub-groups and the basis of the norm.

Additive: three new columns with defaults (existing wagon rows are unchanged) and a wider section check (adds 'lubricants').

Revision ID: 0045_repair_norm_groups
Revises: 0044_repair_norm_items
"""
from alembic import op
import sqlalchemy as sa

revision = "0045_repair_norm_groups"
down_revision = "0044_repair_norm_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("repair_norm_items", sa.Column("norm_group", sa.Text(), nullable=False, server_default=sa.text("''")))
    op.add_column("repair_norm_items", sa.Column("group_name", sa.Text()))
    op.add_column("repair_norm_items", sa.Column("basis", sa.Text(), nullable=False, server_default=sa.text("'per_repair'")))
    op.create_check_constraint("ck_repair_norm_items_basis", "repair_norm_items", "basis IN ('per_repair','per_month_per_unit')")
    op.drop_constraint("ck_repair_norm_items_section", "repair_norm_items", type_="check")
    op.create_check_constraint("ck_repair_norm_items_section", "repair_norm_items", "section IN ('materials','spare_parts','lubricants')")
    op.drop_index("ix_repair_norm_items_set", table_name="repair_norm_items")
    op.create_index("ix_repair_norm_items_set", "repair_norm_items", ["work_type_id", "asset_type", "asset_model_id", "norm_group", "seq"])


def downgrade() -> None:
    op.execute("DELETE FROM repair_norm_items WHERE section = 'lubricants' OR norm_group <> '' OR basis <> 'per_repair'")
    op.drop_index("ix_repair_norm_items_set", table_name="repair_norm_items")
    op.create_index("ix_repair_norm_items_set", "repair_norm_items", ["work_type_id", "asset_type", "asset_model_id", "seq"])
    op.drop_constraint("ck_repair_norm_items_section", "repair_norm_items", type_="check")
    op.create_check_constraint("ck_repair_norm_items_section", "repair_norm_items", "section IN ('materials','spare_parts')")
    op.drop_constraint("ck_repair_norm_items_basis", "repair_norm_items", type_="check")
    op.drop_column("repair_norm_items", "basis")
    op.drop_column("repair_norm_items", "group_name")
    op.drop_column("repair_norm_items", "norm_group")
