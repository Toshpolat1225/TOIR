"""Weighing-scale (Vesovoy) data: posts, trains, weighed units, matched carriages and operator corrections.

Additive only: six new tables and two permission codes; nothing existing changes. Data is pushed by the Windows collector
(`scripts/scales_collector`) from the two scale PCs and matched to GTK trains / TOIR assets by `app.services.scales`.

Revision ID: 0034_scales
Revises: 0033_wialon_position
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0034_scales"
down_revision = "0033_wialon_position"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scale_posts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.Text, nullable=False, unique=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("tare_default_t", sa.Numeric(8, 2)),
        sa.Column("capacity_norm_t", sa.Numeric(8, 2)),
        sa.Column("last_pull_at", sa.DateTime(timezone=True)),
        sa.Column("last_weighing_at", sa.DateTime(timezone=True)),
        sa.Column("last_src_train_id", sa.Integer),
        sa.Column("last_src_weighing_id", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "scale_cargo",
        sa.Column("code", sa.Integer, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
    )
    op.create_table(
        "scale_trains",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scale_posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("src_id", sa.Integer, nullable=False),
        sa.Column("registered_on", sa.Date),
        sa.Column("loco_number", sa.Text),
        sa.Column("declared_wagons", sa.Integer),
        sa.Column("reported_weight_t", sa.Numeric(10, 2)),
        sa.Column("doc_weight_t", sa.Numeric(10, 2)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("cargo_code", sa.Integer),
        sa.Column("excavator", sa.Integer),
        sa.Column("operator_code", sa.Integer),
        sa.Column("row_hash", sa.Text, nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("wagon_rows", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("dump_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("traction_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("net_total_t", sa.Numeric(10, 2)),
        sa.Column("net_source", sa.Text),
        sa.Column("loco_asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fixed_assets.id", ondelete="SET NULL")),
        sa.Column("loco_gtk_id", sa.Integer),
        sa.Column("gtk_train_id", sa.Integer),
        sa.Column("carriages_total", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("carriages_linked", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("match_status", sa.Text, nullable=False, server_default=sa.text("'pending'")),
        sa.Column("match_method", sa.Text),
        sa.Column("flags", postgresql.ARRAY(sa.Text), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("matched_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("post_id", "src_id", name="uq_scale_trains_post_src"),
        sa.CheckConstraint(
            "match_status IN ('pending','ok','no_loco','no_gtk_train','excluded')", name="ck_scale_trains_match_status"
        ),
    )
    op.create_index("ix_scale_trains_started", "scale_trains", ["started_at"])
    op.create_index("ix_scale_trains_loco_asset_started", "scale_trains", ["loco_asset_id", "started_at"])
    op.create_index(
        "ix_scale_trains_open",
        "scale_trains",
        ["match_status"],
        postgresql_where=sa.text("match_status <> 'ok' AND match_status <> 'excluded'"),
    )
    op.create_table(
        "scale_weighings",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("train_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scale_trains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("src_id", sa.Integer, nullable=False),
        sa.Column("position", sa.Integer),
        sa.Column("unit_label", sa.Text),
        sa.Column("gross_t", sa.Numeric(8, 2)),
        sa.Column("tare_t", sa.Numeric(8, 2)),
        sa.Column("net_t", sa.Numeric(8, 2)),
        sa.Column("capacity_t", sa.Numeric(8, 2)),
        sa.Column("overload_t", sa.Numeric(8, 2)),
        sa.Column("speed_kmh", sa.Numeric(6, 2)),
        sa.Column("axles", sa.SmallInteger),
        sa.Column("weighed_at", sa.DateTime(timezone=True)),
        sa.Column("unit_kind", sa.Text, nullable=False, server_default=sa.text("'dump'")),
        sa.UniqueConstraint("train_id", "src_id", name="uq_scale_weighings_train_src"),
        sa.CheckConstraint("unit_kind IN ('traction','dump')", name="ck_scale_weighings_unit_kind"),
    )
    op.create_table(
        "scale_train_carriages",
        sa.Column("train_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scale_trains.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("carriage_gtk_id", sa.Integer, primary_key=True),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fixed_assets.id", ondelete="SET NULL")),
        sa.Column("ord", sa.Integer, nullable=False),
    )
    op.create_index("ix_scale_train_carriages_asset", "scale_train_carriages", ["asset_id"])
    op.create_table(
        "scale_corrections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("loco_number", sa.Text),
        sa.Column("train_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scale_trains.id", ondelete="CASCADE")),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fixed_assets.id", ondelete="CASCADE")),
        sa.Column("gtk_train_id", sa.Integer),
        sa.Column("note", sa.Text),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("kind IN ('loco_alias','train_exclude','train_gtk')", name="ck_scale_corrections_kind"),
        sa.CheckConstraint(
            "(kind = 'loco_alias' AND loco_number IS NOT NULL AND asset_id IS NOT NULL)"
            " OR (kind = 'train_exclude' AND train_id IS NOT NULL)"
            " OR (kind = 'train_gtk' AND train_id IS NOT NULL AND gtk_train_id IS NOT NULL)",
            name="ck_scale_corrections_shape",
        ),
    )
    op.create_index(
        "uq_scale_corrections_alias", "scale_corrections", ["loco_number"], unique=True,
        postgresql_where=sa.text("kind = 'loco_alias' AND is_active"),
    )
    op.create_index(
        "uq_scale_corrections_train", "scale_corrections", ["train_id", "kind"], unique=True,
        postgresql_where=sa.text("kind <> 'loco_alias' AND is_active"),
    )
    # permissions: the master role never sees the scales (same as GTK); operator edits, management reads
    op.execute(
        """
        INSERT INTO permissions(code, module, action, label) VALUES
            ('scales.view', 'scales', 'view', 'Weighing scales data'),
            ('scales.manage', 'scales', 'manage_reference_data', 'Weighing scales corrections')
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions(role, permission_code, granted)
        VALUES
            ('admin', 'scales.view', true), ('operator', 'scales.view', true), ('management', 'scales.view', true), ('master', 'scales.view', false),
            ('admin', 'scales.manage', true), ('operator', 'scales.manage', true), ('management', 'scales.manage', false), ('master', 'scales.manage', false)
        ON CONFLICT (role, permission_code) DO UPDATE SET granted = EXCLUDED.granted
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE permission_code IN ('scales.view', 'scales.manage')")
    op.execute("DELETE FROM permissions WHERE code IN ('scales.view', 'scales.manage')")
    op.drop_table("scale_corrections")
    op.drop_table("scale_train_carriages")
    op.drop_table("scale_weighings")
    op.drop_table("scale_trains")
    op.drop_table("scale_cargo")
    op.drop_table("scale_posts")
