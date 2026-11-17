"""Per-car cargo for the weighing scales: pair each dump car's weighing with its GTK carriage by sequence.

Additive only: two nullable columns on `scale_train_carriages` (the scale position paired with the car and the car's own net).
Existing rows keep NULL (= only the train average is known) until the next re-match fills them.

Revision ID: 0035_scale_car_net
Revises: 0034_scales
"""
from alembic import op
import sqlalchemy as sa

revision = "0035_scale_car_net"
down_revision = "0034_scales"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scale_train_carriages", sa.Column("unit_position", sa.Integer, nullable=True))
    op.add_column("scale_train_carriages", sa.Column("net_t", sa.Numeric(8, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("scale_train_carriages", "net_t")
    op.drop_column("scale_train_carriages", "unit_position")
