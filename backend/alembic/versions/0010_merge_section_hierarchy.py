"""Merge organization hierarchy and permission migration branches.

Revision ID: 0010_merge_section_hierarchy
Revises: 0008_safe_section_hierarchy, 0009_user_active_permission
"""

revision = "0010_merge_section_hierarchy"
down_revision = (
    "0008_safe_section_hierarchy",
    "0009_user_active_permission",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
