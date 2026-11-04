"""Add read-only GTK source mirrors and sync history."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0013_gtk_source"
down_revision = "0012_wialon_units"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gtk_locomotives",
        sa.Column("gtk_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Text()),
        sa.Column("garage_number", sa.Text()),
        sa.Column("inventory_number", sa.Text()),
        sa.Column("model_name", sa.Text()),
        sa.Column("vehicle_type_name", sa.Text()),
        sa.Column("division_name", sa.Text()),
        sa.Column("start_expl_date", sa.DateTime(timezone=True)),
        sa.Column("end_expl_date", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("checkpoint_mileage", sa.Numeric(16, 2)),
        sa.Column("checkpoint_at", sa.DateTime(timezone=True)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_gtk_locomotives_name", "gtk_locomotives", ["name"])
    op.create_table(
        "gtk_carriages",
        sa.Column("gtk_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Text()),
        sa.Column("reg_number", sa.Text()),
        sa.Column("inventory_number", sa.Text()),
        sa.Column("model_name", sa.Text()),
        sa.Column("start_expl_date", sa.DateTime(timezone=True)),
        sa.Column("end_expl_date", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_loaded", sa.Boolean()),
        sa.Column("is_not_serviceable", sa.Boolean()),
        sa.Column("lat", sa.Numeric(10, 7)),
        sa.Column("lon", sa.Numeric(10, 7)),
        sa.Column("state_duration_s", sa.Integer()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_gtk_carriages_name", "gtk_carriages", ["name"])
    op.create_index("ix_gtk_carriages_reg_number", "gtk_carriages", ["reg_number"])
    op.create_table(
        "gtk_trains",
        sa.Column("gtk_id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.Text()),
        sa.Column("title", sa.Text()),
        sa.Column("begin_time", sa.DateTime(timezone=True)),
        sa.Column("end_time", sa.DateTime(timezone=True)),
        sa.Column("is_open", sa.Boolean(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_gtk_trains_number", "gtk_trains", ["number"])
    op.create_table(
        "gtk_train_members",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("train_gtk_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("object_gtk_id", sa.Integer(), nullable=False),
        sa.Column("is_main", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("gtk_begin_time", sa.DateTime(timezone=True)),
        sa.Column("observed_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_to", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "kind IN ('locomotive','carriage')", name="ck_gtk_train_members_kind"
        ),
    )
    op.create_index(
        "uq_gtk_train_members_open",
        "gtk_train_members",
        ["train_gtk_id", "kind", "object_gtk_id"],
        unique=True,
        postgresql_where=sa.text("observed_to IS NULL"),
    )
    op.create_index(
        "ix_gtk_train_members_object",
        "gtk_train_members",
        ["kind", "object_gtk_id"],
    )
    op.create_table(
        "gtk_sync_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("counts", postgresql.JSONB()),
        sa.Column("quality", postgresql.JSONB()),
        sa.Column("error", sa.Text()),
        sa.CheckConstraint(
            "status IN ('ok','error','parse_error','suspicious','login_failed')",
            name="ck_gtk_sync_runs_status",
        ),
    )
    op.create_index("ix_gtk_sync_runs_started_at", "gtk_sync_runs", ["started_at"])

    op.execute(
        """
        INSERT INTO permissions(code, module, action, label) VALUES
            ('gtk.view', 'gtk', 'view', 'GTK source data'),
            ('gtk.manage', 'gtk', 'manage_reference_data', 'GTK synchronization')
        ON CONFLICT (code) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions(role, permission_code, granted)
        VALUES
            ('admin', 'gtk.view', true),
            ('operator', 'gtk.view', true),
            ('management', 'gtk.view', true),
            ('admin', 'gtk.manage', true),
            ('operator', 'gtk.manage', true),
            ('master', 'gtk.view', false),
            ('master', 'gtk.manage', false),
            ('management', 'gtk.manage', false)
        ON CONFLICT (role, permission_code) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM permissions WHERE code IN ('gtk.view','gtk.manage')")
    op.drop_index("ix_gtk_sync_runs_started_at", table_name="gtk_sync_runs")
    op.drop_table("gtk_sync_runs")
    op.drop_index("ix_gtk_train_members_object", table_name="gtk_train_members")
    op.drop_index("uq_gtk_train_members_open", table_name="gtk_train_members")
    op.drop_table("gtk_train_members")
    op.drop_index("ix_gtk_trains_number", table_name="gtk_trains")
    op.drop_table("gtk_trains")
    op.drop_index("ix_gtk_carriages_reg_number", table_name="gtk_carriages")
    op.drop_index("ix_gtk_carriages_name", table_name="gtk_carriages")
    op.drop_table("gtk_carriages")
    op.drop_index("ix_gtk_locomotives_name", table_name="gtk_locomotives")
    op.drop_table("gtk_locomotives")
