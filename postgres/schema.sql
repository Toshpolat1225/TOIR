-- =====================================================================
-- TOIR — yagona PostgreSQL 16 sxemasi
-- Prinsiplar:
--   * barcha bog'lanishlar FK orqali (matn maydonlari yo'q)
--   * JSONB o'rniga normallashtirilgan jadvallar (repair_items, items)
--   * bitta status lug'ati, bitta ТО-chegara manbai (maintenance_intervals)
--   * auth.users/profiles o'rniga oddiy users jadvali
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS citext;     -- email uchun

-- ---------- umumiy trigger: updated_at ----------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =====================================================================
-- 1. SPRAVOCHNIKLAR: bo'limlar, uchastkalar, xodimlar
-- =====================================================================
CREATE TABLE departments (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL UNIQUE,
    color       text NOT NULL DEFAULT '#3b82f6',
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Uchastka (ПТОВ, ПТОЛ, ВРП, ЭЛ_ДЕПО) har doim bitta bo'limga tegishli
CREATE TABLE sections (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name           text NOT NULL,
    department_id  uuid REFERENCES departments(id) ON DELETE SET NULL,
    parent_id      uuid REFERENCES sections(id) ON DELETE SET NULL,
    unit_type      text NOT NULL DEFAULT 'section',
    code           text,
    is_active      boolean NOT NULL DEFAULT true,
    is_archived    boolean NOT NULL DEFAULT false,
    sort_order     integer NOT NULL DEFAULT 0,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE sections
    ADD CONSTRAINT ck_sections_unit_type_supported
    CHECK (unit_type IN ('department', 'division', 'section', 'team'));
CREATE INDEX ix_sections_department ON sections(department_id);
CREATE INDEX ix_sections_parent ON sections(parent_id);
CREATE INDEX ix_sections_type ON sections(unit_type);

CREATE FUNCTION enforce_section_hierarchy()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    parent_unit_type text;
    parent_is_archived boolean;
BEGIN
    PERFORM pg_advisory_xact_lock(1936028276);

    IF NEW.parent_id IS NOT NULL THEN
        SELECT unit_type, is_archived
          INTO parent_unit_type, parent_is_archived
          FROM sections
         WHERE id = NEW.parent_id;

        IF parent_unit_type IS NULL THEN
            RAISE EXCEPTION 'Parent section does not exist'
                USING ERRCODE = '23503';
        END IF;
        IF parent_is_archived THEN
            RAISE EXCEPTION 'Cannot assign an archived parent section'
                USING ERRCODE = '23514';
        END IF;
        IF NOT (
            (NEW.unit_type = 'division' AND parent_unit_type IN ('department', 'division'))
            OR (NEW.unit_type = 'section' AND parent_unit_type IN ('department', 'division', 'section'))
            OR (NEW.unit_type = 'team' AND parent_unit_type IN ('division', 'section', 'team'))
        ) THEN
            RAISE EXCEPTION 'Invalid typed parent-child relationship'
                USING ERRCODE = '23514';
        END IF;

        IF EXISTS (
            WITH RECURSIVE ancestors(id, parent_id, visited) AS (
                SELECT id, parent_id, ARRAY[id]
                FROM sections
                WHERE id = NEW.parent_id
                UNION ALL
                SELECT parent.id, parent.parent_id, ancestors.visited || parent.id
                FROM sections parent
                JOIN ancestors ON parent.id = ancestors.parent_id
                WHERE NOT parent.id = ANY(ancestors.visited)
            )
            SELECT 1 FROM ancestors WHERE id = NEW.id
        ) THEN
            RAISE EXCEPTION 'Section cannot be assigned beneath itself or its descendants'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM sections child
        WHERE child.parent_id = NEW.id
          AND NOT (
              (child.unit_type = 'division' AND NEW.unit_type IN ('department', 'division'))
              OR (child.unit_type = 'section' AND NEW.unit_type IN ('department', 'division', 'section'))
              OR (child.unit_type = 'team' AND NEW.unit_type IN ('division', 'section', 'team'))
          )
    ) THEN
        RAISE EXCEPTION 'Changing this unit type would invalidate a child relationship'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.is_archived AND EXISTS (
        SELECT 1 FROM sections child
        WHERE child.parent_id = NEW.id AND NOT child.is_archived
    ) THEN
        RAISE EXCEPTION 'Move or archive child units before archiving this unit'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$;
CREATE TRIGGER trg_sections_hierarchy
BEFORE INSERT OR UPDATE OF parent_id, unit_type, is_archived
ON sections
FOR EACH ROW
EXECUTE FUNCTION enforce_section_hierarchy();

-- =====================================================================
-- 2. FOYDALANUVCHILAR
-- =====================================================================
CREATE TABLE users (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email            citext NOT NULL UNIQUE,
    full_name        text NOT NULL,
    hashed_password  text NOT NULL,
    role             text NOT NULL CHECK (role IN ('admin','operator','master','management')),
    section_id       uuid REFERENCES sections(id) ON DELETE SET NULL,
    is_active        boolean NOT NULL DEFAULT true,
    last_login_at    timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    -- master uchastkasiz bo'lishi mumkin emas
    CONSTRAINT ck_master_has_section CHECK (role <> 'master' OR section_id IS NOT NULL)
);

-- Refresh tokenlar (xeshi saqlanadi, tokenning o'zi emas) — logout/revoke uchun
CREATE TABLE refresh_tokens (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  text NOT NULL UNIQUE,
    expires_at  timestamptz NOT NULL,
    revoked_at  timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_refresh_tokens_user ON refresh_tokens(user_id);

CREATE TABLE permissions (
    code   text PRIMARY KEY,
    module text NOT NULL,
    action text NOT NULL,
    label  text NOT NULL,
    CONSTRAINT ck_permissions_action CHECK (
        action IN (
            'view','create','update','delete','export','approve',
            'manage_permissions','manage_users','manage_reference_data'
        )
    )
);

CREATE TABLE role_permissions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    role text NOT NULL,
    permission_code text NOT NULL REFERENCES permissions(code) ON DELETE CASCADE,
    granted boolean NOT NULL DEFAULT false,
    CONSTRAINT ck_role_permissions_role
        CHECK (role IN ('admin','operator','master','management')),
    CONSTRAINT uq_role_permissions_role_code UNIQUE (role, permission_code)
);
CREATE INDEX ix_role_permissions_role ON role_permissions(role);

CREATE TABLE permission_audit (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    target_role text NOT NULL,
    permission_code text NOT NULL,
    previous_granted boolean NOT NULL,
    new_granted boolean NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_permission_audit_role
        CHECK (target_role IN ('admin','operator','master','management'))
);
CREATE INDEX ix_permission_audit_created_at ON permission_audit(created_at);

CREATE TABLE audit_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    action text NOT NULL CHECK (action IN ('create','update','delete','login','logout','other')),
    actor_type text NOT NULL CHECK (actor_type IN ('user','system','anonymous')),
    actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    actor_name text,
    module text NOT NULL,
    route text NOT NULL,
    object_type text,
    object_id text,
    object_label text,
    old_values jsonb,
    new_values jsonb,
    details jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_audit_logs_created_at ON audit_logs(created_at);
CREATE INDEX ix_audit_logs_actor_created ON audit_logs(actor_user_id, created_at);
CREATE INDEX ix_audit_logs_action_created ON audit_logs(action, created_at);
CREATE INDEX ix_audit_logs_module_created ON audit_logs(module, created_at);

-- Persistent per-account/IP failed-login window; key_hash does not contain raw credentials.
CREATE TABLE login_attempts (
    id         bigserial PRIMARY KEY,
    key_hash   varchar(64) NOT NULL,
    failed_at  timestamptz NOT NULL
);
CREATE INDEX ix_login_attempts_key_failed ON login_attempts(key_hash, failed_at);
CREATE INDEX ix_login_attempts_failed_at ON login_attempts(failed_at);

CREATE TABLE employees (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tab_number  text NOT NULL UNIQUE,
    full_name   text NOT NULL,
    position    text,
    section_id  uuid REFERENCES sections(id) ON DELETE SET NULL,
    location_id text,
    is_active   boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_employees_section ON employees(section_id);

-- =====================================================================
-- 3. ASOSIY VOSITALAR (ОС)
-- =====================================================================
CREATE TABLE fixed_asset_types (
    code       text PRIMARY KEY,
    is_active  boolean NOT NULL DEFAULT true,
    color      text NOT NULL DEFAULT 'blue' CHECK (color IN ('blue','green','amber','orange','red','gray','purple'))
);
CREATE TABLE fixed_asset_statuses (
    code       text PRIMARY KEY,
    is_active  boolean NOT NULL DEFAULT true,
    behavior   text NOT NULL DEFAULT 'operational' CHECK (behavior IN ('operational','maintenance','repair','out_of_service')),
    color      text NOT NULL DEFAULT 'green' CHECK (color IN ('blue','green','amber','orange','red','gray','purple'))
);
CREATE TABLE asset_models (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name            text NOT NULL,
    name_normalized text NOT NULL,
    asset_type      text NOT NULL REFERENCES fixed_asset_types(code) ON UPDATE CASCADE ON DELETE RESTRICT,
    series          text,
    CONSTRAINT uq_asset_models_name_normalized UNIQUE (name_normalized)
);

CREATE TABLE fixed_assets (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    inv_number           text NOT NULL,
    asset_type           text NOT NULL REFERENCES fixed_asset_types(code) ON UPDATE CASCADE ON DELETE RESTRICT,
    section_id           uuid REFERENCES sections(id) ON DELETE SET NULL,
    serial_number        text,
    model_id             uuid REFERENCES asset_models(id) ON DELETE RESTRICT,
    accounting_inv_number text,
    commissioned_at      date,
    decommissioned_at    date,
    inv_number_is_provisional boolean DEFAULT false,
    status               text NOT NULL DEFAULT 'operational'
                         REFERENCES fixed_asset_statuses(code) ON UPDATE CASCADE ON DELETE RESTRICT,
    year_built           integer,
    -- Operational maintenance and telemetry fields follow the passport fields.
    mileage              numeric(12,2) NOT NULL DEFAULT 0,
    last_maint_date      date,
    next_maint_date      date,
    initial_cost         numeric(16,2),
    owner                text,
    -- Wialon
    wialon_id            varchar(100) UNIQUE,
    -- GTK
    gtk_id               varchar(100) CONSTRAINT uq_fixed_assets_gtk_id UNIQUE,
    wialon_last_sync     timestamptz,
    wialon_speed         numeric(6,2),
    wialon_online        boolean NOT NULL DEFAULT false,
    -- ML natijalari
    failure_probability  numeric(5,4),
    health_score         numeric(5,2),
    predicted_failure_km numeric(12,2),
    last_ml_update       timestamptz,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_fixed_assets_year_built_min
        CHECK (year_built IS NULL OR year_built >= 1900),
    CONSTRAINT ck_fixed_assets_commissioned_at_year_built
        CHECK (CASE WHEN commissioned_at IS NULL OR year_built IS NULL
                    OR year_built < 1 OR year_built > 9999 THEN true
                    ELSE commissioned_at >= make_date(year_built, 1, 1) END),
    CONSTRAINT ck_fixed_assets_decommissioned_at_commissioned_at
        CHECK (decommissioned_at IS NULL OR commissioned_at IS NULL
               OR decommissioned_at >= commissioned_at)
);
CREATE INDEX ix_assets_type_status ON fixed_assets(asset_type, status);
CREATE INDEX ix_assets_section     ON fixed_assets(section_id);
CREATE INDEX ix_fixed_assets_model_id ON fixed_assets(model_id);
CREATE INDEX ix_fixed_assets_inv_number
    ON fixed_assets(inv_number);
CREATE UNIQUE INDEX uq_fixed_assets_accounting_inv_number
    ON fixed_assets(accounting_inv_number) WHERE accounting_inv_number IS NOT NULL;
CREATE INDEX ix_fixed_assets_type_model_serial
    ON fixed_assets(asset_type, model_id, serial_number)
    WHERE model_id IS NOT NULL AND serial_number IS NOT NULL;

CREATE TABLE wialon_counter_state (
    asset_id uuid PRIMARY KEY REFERENCES fixed_assets(id) ON DELETE CASCADE,
    baseline_cnm numeric(16,2),
    last_cnm numeric(16,2),
    last_cnm_at timestamptz,
    baseline_cneh numeric(14,3),
    last_cneh numeric(14,3),
    last_cneh_at timestamptz,
    engine_hours numeric(12,3),
    suspect_absolute boolean NOT NULL DEFAULT false,
    last_status text,
    last_reason text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE wialon_rejected_readings (
    id bigserial PRIMARY KEY,
    asset_id uuid NOT NULL REFERENCES fixed_assets(id) ON DELETE CASCADE,
    counter text NOT NULL CHECK (counter IN ('mileage','engine_hours')),
    value numeric(18,3),
    previous_value numeric(18,3),
    reading_at timestamptz,
    reason text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_wialon_rejected_asset_time
    ON wialon_rejected_readings(asset_id, created_at DESC);

CREATE TABLE wialon_units (
    unit_id varchar(100) PRIMARY KEY,
    name text NOT NULL,
    cnm numeric(16,2),
    cneh numeric(14,3),
    calc_flags integer,
    speed numeric(6,2),
    last_message_at timestamptz,
    suspect_absolute boolean NOT NULL DEFAULT false,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_synced_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_wialon_units_name ON wialon_units(name);
CREATE INDEX ix_wialon_units_last_message_at ON wialon_units(last_message_at);

CREATE TABLE asset_source_links (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id     uuid NOT NULL REFERENCES fixed_assets(id) ON DELETE CASCADE,
    source       varchar(20) NOT NULL
                 CHECK (source IN ('wialon','gtk','vesavoy','onec')),
    external_id  varchar(100) NOT NULL,
    external_name text,
    status       varchar(20) NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active','ended')),
    link_method  varchar(20) NOT NULL DEFAULT 'manual'
                 CHECK (link_method IN ('manual','migrated','import')),
    linked_by    uuid REFERENCES users(id) ON DELETE SET NULL,
    linked_at    timestamptz NOT NULL DEFAULT now(),
    unlinked_at  timestamptz,
    note         text
);
CREATE UNIQUE INDEX uq_asset_source_links_source_external_active
    ON asset_source_links(source, external_id) WHERE status = 'active';
CREATE UNIQUE INDEX uq_asset_source_links_asset_source_active
    ON asset_source_links(asset_id, source) WHERE status = 'active';
CREATE INDEX ix_asset_source_links_asset_time
    ON asset_source_links(asset_id, linked_at);

CREATE TABLE asset_field_changes (
    id           bigserial PRIMARY KEY,
    asset_id     uuid NOT NULL REFERENCES fixed_assets(id) ON DELETE CASCADE,
    field        varchar(100) NOT NULL,
    old_value    jsonb,
    new_value    jsonb,
    source       varchar(20) NOT NULL,
    kind         varchar(20) NOT NULL
                 CHECK (kind IN ('auto_fill','conflict','manual')),
    status       varchar(20) NOT NULL
                 CHECK (status IN ('applied','pending','accepted','rejected')),
    created_at   timestamptz NOT NULL DEFAULT now(),
    resolved_by  uuid REFERENCES users(id) ON DELETE SET NULL,
    resolved_at  timestamptz
);
CREATE INDEX ix_asset_field_changes_status_created
    ON asset_field_changes(status, created_at);
CREATE INDEX ix_asset_field_changes_asset_field_status
    ON asset_field_changes(asset_id, field, status);

CREATE TABLE mileage_history (
    id           bigserial PRIMARY KEY,
    asset_id     uuid NOT NULL REFERENCES fixed_assets(id) ON DELETE CASCADE,
    mileage      numeric(12,2) NOT NULL,
    source       text NOT NULL DEFAULT 'wialon' CHECK (source IN ('wialon','manual','gtk')),
    recorded_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_mileage_asset_time ON mileage_history(asset_id, recorded_at DESC);

CREATE TABLE gtk_locomotives (
    gtk_id           integer PRIMARY KEY,
    name             text,
    garage_number    text,
    inventory_number text,
    model_name       text,
    vehicle_type_name text,
    division_name    text,
    start_expl_date  timestamptz,
    end_expl_date    timestamptz,
    is_active        boolean NOT NULL,
    first_seen_at    timestamptz NOT NULL DEFAULT now(),
    last_synced_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_gtk_locomotives_name ON gtk_locomotives(name);

CREATE TABLE gtk_carriages (
    gtk_id              integer PRIMARY KEY,
    name                text,
    reg_number          text,
    inventory_number    text,
    model_name          text,
    start_expl_date     timestamptz,
    end_expl_date       timestamptz,
    is_active           boolean NOT NULL,
    is_loaded           boolean,
    is_not_serviceable  boolean,
    lat                 numeric(10,7),
    lon                 numeric(10,7),
    state_duration_s    integer,
    first_seen_at       timestamptz NOT NULL DEFAULT now(),
    last_synced_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_gtk_carriages_name ON gtk_carriages(name);
CREATE INDEX ix_gtk_carriages_reg_number ON gtk_carriages(reg_number);

CREATE TABLE gtk_trains (
    gtk_id         integer PRIMARY KEY,
    number         text,
    title          text,
    begin_time     timestamptz,
    end_time       timestamptz,
    is_open        boolean NOT NULL,
    last_synced_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_gtk_trains_number ON gtk_trains(number);

CREATE TABLE gtk_train_members (
    id             bigserial PRIMARY KEY,
    train_gtk_id   integer NOT NULL,
    kind           text NOT NULL CONSTRAINT ck_gtk_train_members_kind
                   CHECK (kind IN ('locomotive','carriage')),
    object_gtk_id  integer NOT NULL,
    is_main        boolean NOT NULL DEFAULT false,
    ord            integer NOT NULL,
    gtk_begin_time timestamptz,
    observed_from  timestamptz NOT NULL,
    observed_to    timestamptz
);
CREATE UNIQUE INDEX uq_gtk_train_members_open
    ON gtk_train_members(train_gtk_id, kind, object_gtk_id)
    WHERE observed_to IS NULL;
CREATE INDEX ix_gtk_train_members_object
    ON gtk_train_members(kind, object_gtk_id);

CREATE TABLE gtk_sync_runs (
    id          bigserial PRIMARY KEY,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status      text NOT NULL CONSTRAINT ck_gtk_sync_runs_status
                CHECK (status IN ('ok','error','parse_error','suspicious','login_failed')),
    counts      jsonb,
    quality     jsonb,
    error       text
);
CREATE INDEX ix_gtk_sync_runs_started_at ON gtk_sync_runs(started_at);

CREATE TABLE gtk_wagon_mileage_log (
    id             bigserial PRIMARY KEY,
    wagon_asset_id uuid NOT NULL REFERENCES fixed_assets(id) ON DELETE CASCADE,
    loco_asset_id  uuid NOT NULL,
    train_gtk_id   integer NOT NULL,
    period_from    timestamptz NOT NULL,
    period_to      timestamptz NOT NULL,
    km             numeric(12,2) NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_gtk_wagon_mileage_log_wagon_period
    ON gtk_wagon_mileage_log(wagon_asset_id, period_to);
CREATE INDEX ix_gtk_wagon_mileage_log_train
    ON gtk_wagon_mileage_log(train_gtk_id);

CREATE TABLE gtk_locomotive_mileage_checkpoints (
    locomotive_gtk_id   integer PRIMARY KEY,
    locomotive_asset_id uuid NOT NULL UNIQUE REFERENCES fixed_assets(id) ON DELETE CASCADE,
    mileage             numeric(12,2) NOT NULL,
    checkpoint_at       timestamptz NOT NULL
);

CREATE TABLE wialon_settings (
    id                     smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),  -- bitta qator
    host                   text,
    token                  text,           -- ilovada shifrlab saqlang
    sync_interval_minutes  integer NOT NULL DEFAULT 5,
    auto_sync_enabled      boolean NOT NULL DEFAULT true,
    last_sync_at           timestamptz,
    last_sync_status       text,
    updated_at             timestamptz NOT NULL DEFAULT now()
);

-- =====================================================================
-- 4. ISH TURLARI, ТО INTERVALLARI (BITTA HAQIQAT MANBAI)
-- =====================================================================
CREATE TABLE work_types (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code        text NOT NULL UNIQUE,                  -- ТО-1, ТР-2, ТО-1В ...
    name        text NOT NULL,
    description text,
    unit_type   text NOT NULL CHECK (unit_type IN ('locomotive','wagon')),
    sort_order  integer NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE work_subtasks (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    work_type_id  uuid NOT NULL REFERENCES work_types(id) ON DELETE CASCADE,
    name          text NOT NULL,
    sort_order    integer NOT NULL DEFAULT 0
);
CREATE INDEX ix_subtasks_work_type ON work_subtasks(work_type_id);

-- ТО chegaralarining yagona manbai (trigger/route/receiver'dagi qattiq qiymatlar o'rniga)
CREATE TABLE maintenance_intervals (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    work_type_id   uuid REFERENCES work_types(id) ON DELETE SET NULL,
    code           text NOT NULL UNIQUE,
    name           text NOT NULL,
    interval_km    numeric(12,2),
    interval_days  integer,
    asset_types    text[] NOT NULL DEFAULT '{locomotive,diesel}',
    warn_percent   numeric(5,2) NOT NULL DEFAULT 10,   -- chegaraga shuncha % qolganda ogohlantirish
    is_active      boolean NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_interval_defined CHECK (interval_km IS NOT NULL OR interval_days IS NOT NULL)
);

-- =====================================================================
-- 5. TMC NOMENKLATURASI VA NORMATIVLAR
-- =====================================================================
CREATE TABLE nomenclature (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    department_id  uuid NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    name           text NOT NULL,
    code           text,
    unit           text NOT NULL DEFAULT 'шт.',
    extra          jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (department_id, name)
);
CREATE INDEX ix_nomenclature_code ON nomenclature(code);

CREATE TABLE nomenclature_norms (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    nomenclature_id    uuid NOT NULL REFERENCES nomenclature(id) ON DELETE CASCADE,
    department_id      uuid NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    work_type_id       uuid NOT NULL REFERENCES work_types(id) ON DELETE CASCADE,
    standard_quantity  numeric(12,3) NOT NULL,
    avg_price          numeric(14,2) NOT NULL DEFAULT 0,
    min_quantity       numeric(12,3),
    max_quantity       numeric(12,3),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (nomenclature_id, department_id, work_type_id)
);

-- Ish turi bo'yicha TMC avto-to'ldirish shabloni (work_type_tmc + work_type_templates birlashtirildi)
CREATE TABLE work_type_templates (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    work_type_id      uuid NOT NULL REFERENCES work_types(id) ON DELETE CASCADE,
    department_id     uuid REFERENCES departments(id) ON DELETE CASCADE,
    nomenclature_id   uuid REFERENCES nomenclature(id) ON DELETE CASCADE,
    name              text,           -- nomenklaturaga bog'lanmagan qator uchun
    inv_no            text,
    unit              text,
    default_quantity  numeric(12,3) NOT NULL DEFAULT 1,
    is_required       boolean NOT NULL DEFAULT false,
    note              text,
    CONSTRAINT ck_template_target CHECK (nomenclature_id IS NOT NULL OR name IS NOT NULL)
);
CREATE INDEX ix_templates_work_type ON work_type_templates(work_type_id);

-- =====================================================================
-- 6. NARIYAD-BUYURTMALAR
-- Statuslar (UI lug'ati): pending → in_progress → completed | cancelled
-- "overdue" saqlanmaydi, date_end bo'yicha hisoblanadi.
-- =====================================================================
CREATE SEQUENCE work_order_seq;

CREATE TABLE work_orders (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    number                text NOT NULL UNIQUE,      -- НЗ-YYYYMMDD-HHMMSS (serverda yaratiladi)
    fixed_asset_id        uuid NOT NULL REFERENCES fixed_assets(id) ON DELETE RESTRICT,
    section_id            uuid NOT NULL REFERENCES sections(id) ON DELETE RESTRICT,
    department_id         uuid REFERENCES departments(id) ON DELETE SET NULL,
    order_kind            text NOT NULL
                          CHECK (order_kind IN ('planned','unplanned','repair','emergency')),
    status                text NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending','in_progress','completed','cancelled')),
    priority              text NOT NULL DEFAULT 'normal'
                          CHECK (priority IN ('critical','high','normal','low')),
    executor_id           uuid REFERENCES employees(id) ON DELETE SET NULL,   -- tech
    chief_id              uuid REFERENCES employees(id) ON DELETE SET NULL,   -- mas'ul
    description           text NOT NULL,
    note                  text,
    date_start            timestamptz,
    date_end              timestamptz,
    closed_at             timestamptz,
    mileage_at_creation   numeric(12,2),
    mileage_threshold     numeric(12,2),
    created_by            uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_closed_when_completed CHECK (status <> 'completed' OR closed_at IS NOT NULL)
);
CREATE INDEX ix_wo_created        ON work_orders(created_at DESC);
CREATE INDEX ix_wo_asset          ON work_orders(fixed_asset_id);
CREATE INDEX ix_wo_section_status ON work_orders(section_id, status, created_at DESC);
CREATE INDEX ix_wo_open           ON work_orders(status) WHERE status IN ('pending','in_progress');

-- repair_items JSONB o'rniga: nariyaddagi har bir ta'mir turi (ТО-2, ТР-1 ...)
CREATE TABLE work_order_repairs (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    work_order_id  uuid NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
    work_type_id   uuid NOT NULL REFERENCES work_types(id) ON DELETE RESTRICT,
    sort_order     integer NOT NULL DEFAULT 0,
    UNIQUE (work_order_id, work_type_id)
);

-- ...va uning ichidagi TMC qatorlari
CREATE TABLE work_order_items (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    repair_id        uuid NOT NULL REFERENCES work_order_repairs(id) ON DELETE CASCADE,
    nomenclature_id  uuid REFERENCES nomenclature(id) ON DELETE SET NULL,
    name             text NOT NULL,
    inv_no           text,
    unit             text,
    qty              numeric(12,3) NOT NULL CHECK (qty >= 0),
    note             text,
    sort_order       integer NOT NULL DEFAULT 0
);
CREATE INDEX ix_wo_items_repair ON work_order_items(repair_id);
CREATE INDEX ix_wo_items_nom    ON work_order_items(nomenclature_id);

-- =====================================================================
-- 7. TMC HUJJATLARI (Требование-накладная)
-- =====================================================================
CREATE TABLE tmc_documents (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_no         text NOT NULL UNIQUE,
    doc_date       date NOT NULL DEFAULT current_date,
    work_order_id  uuid REFERENCES work_orders(id) ON DELETE SET NULL,
    section_id     uuid REFERENCES sections(id) ON DELETE SET NULL,
    work_type_id   uuid REFERENCES work_types(id) ON DELETE SET NULL,
    warehouse      text,
    issued_by      text,
    accepted_by    text,
    chief          text,
    status         text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','issued','closed')),
    created_by     uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_tmc_docs_wo ON tmc_documents(work_order_id);

CREATE TABLE tmc_document_items (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id      uuid NOT NULL REFERENCES tmc_documents(id) ON DELETE CASCADE,
    nomenclature_id  uuid REFERENCES nomenclature(id) ON DELETE SET NULL,
    name             text NOT NULL,
    inv_no           text,
    unit             text,
    qty              numeric(12,3) NOT NULL CHECK (qty >= 0),
    price            numeric(14,2),
    note             text,
    sort_order       integer NOT NULL DEFAULT 0
);
CREATE INDEX ix_tmc_items_doc ON tmc_document_items(document_id);

-- =====================================================================
-- 8. REJALASHTIRILGAN ТО, TARIX, AI
-- =====================================================================
CREATE TABLE maintenance_plan (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id          uuid NOT NULL REFERENCES fixed_assets(id) ON DELETE CASCADE,
    interval_id       uuid NOT NULL REFERENCES maintenance_intervals(id) ON DELETE RESTRICT,
    status            text NOT NULL DEFAULT 'scheduled'
                      CHECK (status IN ('scheduled','in_progress','completed','cancelled')),
    trigger_mileage   numeric(12,2),
    scheduled_date    date,
    completed_date    date,
    work_order_id     uuid REFERENCES work_orders(id) ON DELETE SET NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (asset_id, interval_id, trigger_mileage)
);
CREATE INDEX ix_plan_status_date ON maintenance_plan(status, scheduled_date);

-- Admin/operator/management-configured daily mileage estimate for maintenance forecasts.
CREATE TABLE maintenance_settings (
    id                  smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    daily_average_km    numeric(10,2) CHECK (daily_average_km IS NULL OR daily_average_km > 0),
    updated_at           timestamptz NOT NULL DEFAULT now()
);

-- Excel'dan import qilinadigan tarixiy sarf (anomaliya tahlili uchun)
CREATE TABLE maintenance_log (
    id                bigserial PRIMARY KEY,
    section_id        uuid REFERENCES sections(id) ON DELETE SET NULL,
    item_name         text NOT NULL,
    qty               numeric(12,3) NOT NULL,
    unit              text,
    equipment         text,
    work_type         text,
    maintenance_date  date
);
CREATE INDEX ix_mlog_section_item ON maintenance_log(section_id, item_name);

CREATE TABLE ai_insights (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id          uuid REFERENCES fixed_assets(id) ON DELETE CASCADE,
    work_order_id     uuid REFERENCES work_orders(id) ON DELETE CASCADE,
    insight_type      text NOT NULL CHECK (insight_type IN ('anomaly','prediction','efficiency')),
    probability       numeric(5,4),
    severity          text NOT NULL DEFAULT 'low' CHECK (severity IN ('low','medium','high','critical')),
    message           text NOT NULL,
    suggested_action  text,
    details           jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_resolved       boolean NOT NULL DEFAULT false,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_insights_created ON ai_insights(created_at DESC);
CREATE INDEX ix_insights_asset   ON ai_insights(asset_id);

-- Daily fleet readiness, captured once on the first dashboard request per day.
CREATE TABLE daily_readiness_snapshots (
    snapshot_date          date NOT NULL,
    scope_key              varchar(40) NOT NULL,
    section_id             uuid,
    asset_count            integer NOT NULL CHECK (asset_count >= 0),
    ready_count            integer NOT NULL CHECK (ready_count >= 0 AND ready_count <= asset_count),
    availability_percent   numeric(5,2) NOT NULL CHECK (availability_percent BETWEEN 0 AND 100),
    created_at             timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_date, scope_key)
);
CREATE INDEX ix_readiness_section_date ON daily_readiness_snapshots(section_id, snapshot_date);

-- =====================================================================
-- 13. TARJIMALAR
-- Eski name maydonlari asl qiymat/fallback bo'lib qoladi; ular avtomatik tarjima qilinmaydi.
-- =====================================================================
CREATE TABLE department_translations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    department_id uuid NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    locale text NOT NULL CONSTRAINT ck_department_translation_locale CHECK (locale = 'ru'),
    name text NOT NULL,
    CONSTRAINT uq_department_translation_locale UNIQUE (department_id, locale)
);
CREATE TABLE section_translations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id uuid NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    locale text NOT NULL CONSTRAINT ck_section_translation_locale CHECK (locale = 'ru'),
    name text NOT NULL,
    CONSTRAINT uq_section_translation_locale UNIQUE (section_id, locale)
);
CREATE TABLE work_type_translations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    work_type_id uuid NOT NULL REFERENCES work_types(id) ON DELETE CASCADE,
    locale text NOT NULL CONSTRAINT ck_work_type_translation_locale CHECK (locale = 'ru'),
    name text NOT NULL,
    CONSTRAINT uq_work_type_translation_locale UNIQUE (work_type_id, locale)
);
CREATE TABLE work_subtask_translations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    work_subtask_id uuid NOT NULL REFERENCES work_subtasks(id) ON DELETE CASCADE,
    locale text NOT NULL CONSTRAINT ck_work_subtask_translation_locale CHECK (locale = 'ru'),
    name text NOT NULL,
    CONSTRAINT uq_work_subtask_translation_locale UNIQUE (work_subtask_id, locale)
);
CREATE TABLE nomenclature_translations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    nomenclature_id uuid NOT NULL REFERENCES nomenclature(id) ON DELETE CASCADE,
    locale text NOT NULL CONSTRAINT ck_nomenclature_translation_locale CHECK (locale = 'ru'),
    name text NOT NULL,
    CONSTRAINT uq_nomenclature_translation_locale UNIQUE (nomenclature_id, locale)
);
CREATE TABLE fixed_asset_type_translations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    type_code text NOT NULL REFERENCES fixed_asset_types(code) ON DELETE CASCADE,
    locale text NOT NULL CONSTRAINT ck_fixed_asset_type_translation_locale CHECK (locale = 'ru'),
    name text NOT NULL,
    CONSTRAINT uq_fixed_asset_type_translation_locale UNIQUE (type_code, locale)
);
CREATE TABLE fixed_asset_status_translations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    status_code text NOT NULL REFERENCES fixed_asset_statuses(code) ON DELETE CASCADE,
    locale text NOT NULL CONSTRAINT ck_fixed_asset_status_translation_locale CHECK (locale = 'ru'),
    name text NOT NULL,
    CONSTRAINT uq_fixed_asset_status_translation_locale UNIQUE (status_code, locale)
);
CREATE UNIQUE INDEX uq_fixed_asset_type_translation_name ON fixed_asset_type_translations(locale, lower(name));
CREATE UNIQUE INDEX uq_fixed_asset_status_translation_name ON fixed_asset_status_translations(locale, lower(name));

-- =====================================================================
-- 9. updated_at triggerlari
-- =====================================================================
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'departments','sections','users','employees','fixed_assets','work_types',
        'maintenance_intervals','nomenclature','nomenclature_norms','work_orders',
        'tmc_documents','maintenance_plan','wialon_settings'
    ] LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_%I_updated BEFORE UPDATE ON %I
             FOR EACH ROW EXECUTE FUNCTION set_updated_at()', t, t);
    END LOOP;
END $$;

-- =====================================================================
-- 10. Realtime: o'zgarishlarni backend'ga LISTEN/NOTIFY orqali yetkazish
--     Backend `toir_changes` kanalini tinglaydi va WebSocket /ws orqali klientlarga uzatadi.
-- =====================================================================
CREATE OR REPLACE FUNCTION notify_change() RETURNS trigger AS $$
DECLARE
    changed_id uuid;
    scopes uuid[] := ARRAY[]::uuid[];
BEGIN
    IF TG_OP <> 'INSERT' THEN
        changed_id := OLD.id;
        IF OLD.section_id IS NOT NULL THEN
            scopes := array_append(scopes, OLD.section_id);
        END IF;
    END IF;
    IF TG_OP <> 'DELETE' THEN
        changed_id := NEW.id;
        IF NEW.section_id IS NOT NULL
           AND NOT (NEW.section_id = ANY(scopes)) THEN
            scopes := array_append(scopes, NEW.section_id);
        END IF;
    END IF;
    PERFORM pg_notify(
        'toir_changes',
        json_build_object(
            'table', TG_TABLE_NAME,
            'op', TG_OP,
            'id', changed_id,
            'section_ids', scopes
        )::text
    );
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_work_orders_notify AFTER INSERT OR UPDATE OR DELETE ON work_orders
    FOR EACH ROW EXECUTE FUNCTION notify_change();
CREATE TRIGGER trg_fixed_assets_notify AFTER INSERT OR UPDATE OR DELETE ON fixed_assets
    FOR EACH ROW EXECUTE FUNCTION notify_change();
CREATE TRIGGER trg_users_notify AFTER INSERT OR UPDATE OR DELETE ON users
    FOR EACH ROW EXECUTE FUNCTION notify_change();

CREATE OR REPLACE FUNCTION fixed_asset_display_name(
    asset_type text,
    serial_number text,
    inv_number text
) RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(
        (
            SELECT fat.name
            FROM fixed_asset_type_translations fat
            WHERE fat.type_code = $1 AND fat.locale = 'ru'
            LIMIT 1
        ),
        $1
    ) || ' ' || COALESCE($2, '') || '-' || $3
$$;

CREATE OR REPLACE VIEW work_order_tmc_details AS
SELECT
    wo.id AS work_order_id,
    wo.number AS work_order_number,
    wo.fixed_asset_id AS asset_id,
    fixed_asset_display_name(fa.asset_type, fa.serial_number, fa.inv_number) AS unit,
    fa.inv_number AS asset_inv_number,
    fa.asset_type AS unit_type,
    wo.section_id,
    s.name AS section,
    wo.department_id,
    wo.status,
    wo.order_kind,
    wo.priority,
    wo.created_at,
    wo.closed_at,
    e.full_name AS tech,
    wt.id AS work_type_id,
    wt.code AS item_kind,
    wt.name AS work_type_name,
    woi.id AS tmc_item_id,
    woi.nomenclature_id,
    COALESCE(n.name, woi.name) AS tmc_name,
    COALESCE(n.code, woi.inv_no) AS tmc_inv_no,
    COALESCE(n.unit, woi.unit) AS tmc_unit,
    woi.qty AS tmc_qty,
    nn.standard_quantity,
    nn.avg_price,
    CASE
        WHEN nn.standard_quantity > 0
            THEN round(((woi.qty - nn.standard_quantity) / nn.standard_quantity * 100)::numeric, 2)
        ELSE NULL
    END AS deviation_percent,
    round((woi.qty * COALESCE(nn.avg_price, 0))::numeric, 2) AS item_cost,
    round((nn.standard_quantity * COALESCE(nn.avg_price, 0))::numeric, 2) AS norm_cost
FROM work_orders wo
JOIN fixed_assets fa ON fa.id = wo.fixed_asset_id
JOIN sections s ON s.id = wo.section_id
LEFT JOIN employees e ON e.id = wo.executor_id
JOIN work_order_repairs wor ON wor.work_order_id = wo.id
JOIN work_types wt ON wt.id = wor.work_type_id
JOIN work_order_items woi ON woi.repair_id = wor.id
LEFT JOIN nomenclature n ON n.id = woi.nomenclature_id
LEFT JOIN nomenclature_norms nn
    ON nn.nomenclature_id = woi.nomenclature_id
    AND nn.department_id = wo.department_id
    AND nn.work_type_id = wor.work_type_id;

CREATE OR REPLACE VIEW executive_summary AS
WITH costs AS (
    SELECT
        wo.id AS work_order_id,
        wo.number,
        wo.fixed_asset_id AS asset_id,
        fixed_asset_display_name(fa.asset_type, fa.serial_number, fa.inv_number) AS unit,
        fa.inv_number AS asset_inv_number,
        fa.asset_type AS unit_type,
        wo.section_id,
        s.name AS section,
        wo.department_id,
        wo.status,
        wo.order_kind,
        wo.priority,
        wo.description,
        wo.created_at,
        wo.closed_at AS closed,
        e.full_name AS tech,
        count(d.tmc_item_id) AS tmc_count,
        coalesce(sum(d.tmc_qty), 0) AS total_qty,
        coalesce(sum(d.item_cost), 0) AS total_cost,
        coalesce(sum(d.norm_cost), 0) AS total_norm_cost,
        avg(d.deviation_percent) AS avg_deviation_percent,
        count(*) FILTER (WHERE d.deviation_percent > 20) AS overrun_count,
        string_agg(DISTINCT d.item_kind, ', ' ORDER BY d.item_kind)
            FILTER (WHERE d.item_kind IS NOT NULL) AS repair_kind,
        wo.mileage_at_creation AS current_mileage
    FROM work_orders wo
    JOIN fixed_assets fa ON fa.id = wo.fixed_asset_id
    JOIN sections s ON s.id = wo.section_id
    LEFT JOIN employees e ON e.id = wo.executor_id
    LEFT JOIN work_order_tmc_details d ON d.work_order_id = wo.id
    GROUP BY
        wo.id, wo.number, wo.fixed_asset_id, fa.asset_type, fa.serial_number,
        fa.inv_number, wo.section_id, s.name, wo.department_id, wo.status,
        wo.order_kind, wo.priority, wo.description, wo.created_at, wo.closed_at,
        e.full_name, wo.mileage_at_creation
),
with_previous AS (
    SELECT
        costs.*,
        lag(current_mileage) OVER (
            PARTITION BY asset_id, repair_kind ORDER BY created_at, work_order_id
        ) AS prev_mileage,
        lag(created_at) OVER (
            PARTITION BY asset_id, repair_kind ORDER BY created_at, work_order_id
        ) AS prev_order_date
    FROM costs
)
SELECT
    *,
    round((total_norm_cost - total_cost)::numeric, 2) AS cost_savings,
    CASE WHEN total_norm_cost > 0
        THEN round(((total_norm_cost - total_cost) / total_norm_cost * 100)::numeric, 2)
        ELSE 0
    END AS savings_percent,
    coalesce(current_mileage - prev_mileage, 0) AS mileage_between_orders,
    extract(day FROM (created_at - prev_order_date)) AS days_between_orders
FROM with_previous;

CREATE OR REPLACE VIEW section_efficiency AS
SELECT
    section_id,
    section,
    count(*) AS total_orders,
    count(*) FILTER (WHERE status = 'completed') AS completed_orders,
    sum(tmc_count) AS total_tmc_items,
    round(sum(total_cost)::numeric, 0) AS total_actual_cost,
    round(sum(total_norm_cost)::numeric, 0) AS total_norm_cost,
    round(sum(cost_savings)::numeric, 0) AS total_savings,
    round(avg(savings_percent)::numeric, 2) AS avg_savings_percent,
    round(avg(avg_deviation_percent)::numeric, 2) AS avg_deviation_percent,
    sum(overrun_count) AS total_overruns,
    round(avg(mileage_between_orders)::numeric, 0) AS avg_mileage_between,
    round(avg(days_between_orders)::numeric, 1) AS avg_days_between
FROM executive_summary
GROUP BY section_id, section;

CREATE OR REPLACE VIEW work_type_efficiency AS
SELECT
    es.section_id,
    es.section,
    d.item_kind AS repair_kind,
    count(DISTINCT d.work_order_id) AS total_orders,
    round(sum(d.item_cost)::numeric, 0) AS total_actual_cost,
    round(sum(d.norm_cost)::numeric, 0) AS total_norm_cost,
    round(sum(d.norm_cost - d.item_cost)::numeric, 0) AS total_savings,
    CASE WHEN sum(d.norm_cost) > 0
        THEN round(((sum(d.norm_cost) - sum(d.item_cost)) / sum(d.norm_cost) * 100)::numeric, 2)
        ELSE 0
    END AS avg_savings_percent,
    round(avg(d.deviation_percent)::numeric, 2) AS avg_deviation_percent,
    round(avg(es.mileage_between_orders)::numeric, 0) AS avg_mileage_between,
    count(*) FILTER (WHERE d.deviation_percent > 20) AS total_overruns
FROM work_order_tmc_details d
JOIN executive_summary es ON es.work_order_id = d.work_order_id
GROUP BY es.section_id, es.section, d.item_kind;

CREATE OR REPLACE VIEW monthly_efficiency AS
SELECT
    date_trunc('month', created_at)::date AS month,
    section_id,
    section,
    count(*) AS orders_count,
    round(sum(total_cost)::numeric, 0) AS actual_cost,
    round(sum(total_norm_cost)::numeric, 0) AS norm_cost,
    round(sum(cost_savings)::numeric, 0) AS savings,
    round(avg(savings_percent)::numeric, 2) AS avg_savings_percent
FROM executive_summary
GROUP BY date_trunc('month', created_at), section_id, section;

CREATE OR REPLACE VIEW ai_insights_summary AS
SELECT
    fa.section_id,
    ai.insight_type,
    ai.severity,
    count(*) AS total_count,
    count(*) FILTER (WHERE NOT ai.is_resolved) AS unresolved_count,
    avg(ai.probability) AS avg_probability,
    max(ai.created_at) AS last_created
FROM ai_insights ai
LEFT JOIN fixed_assets fa ON fa.id = ai.asset_id
WHERE ai.created_at > now() - interval '30 days'
GROUP BY fa.section_id, ai.insight_type, ai.severity;

CREATE OR REPLACE VIEW fleet_health AS
SELECT
    section_id,
    count(*) AS total_assets,
    count(*) FILTER (WHERE failure_probability < 0.2) AS healthy_count,
    count(*) FILTER (WHERE failure_probability >= 0.2 AND failure_probability < 0.5) AS warning_count,
    count(*) FILTER (WHERE failure_probability >= 0.5 AND failure_probability < 0.8) AS risk_count,
    count(*) FILTER (WHERE failure_probability >= 0.8) AS critical_count,
    round(avg(coalesce(health_score, 100))::numeric, 1) AS avg_health_score,
    round((1 - avg(coalesce(failure_probability, 0)))::numeric * 100, 1) AS reliability_percent
FROM fixed_assets
WHERE asset_type IN ('locomotive', 'diesel', 'wagon')
GROUP BY section_id;

CREATE OR REPLACE VIEW maintenance_schedule AS
SELECT
    mp.id AS plan_id,
    mp.asset_id,
    fixed_asset_display_name(fa.asset_type, fa.serial_number, fa.inv_number) AS asset_name,
    fa.inv_number,
    fa.section_id,
    mi.id AS interval_id,
    mi.code AS interval_code,
    mi.name AS interval_name,
    mi.work_type_id,
    mp.status,
    mp.trigger_mileage,
    mp.scheduled_date,
    mp.completed_date,
    mp.work_order_id,
    fa.mileage AS current_mileage,
    CASE WHEN mp.trigger_mileage IS NOT NULL
        THEN mp.trigger_mileage - fa.mileage
        ELSE NULL
    END AS remaining_km
FROM maintenance_plan mp
JOIN fixed_assets fa ON fa.id = mp.asset_id
JOIN maintenance_intervals mi ON mi.id = mp.interval_id
WHERE mi.is_active;

-- =====================================================================
-- Wagon mileage tables (schema exported from Alembic 0028 rehearsal DB)
-- =====================================================================
CREATE TABLE gtk_membership_observations (
    id bigserial PRIMARY KEY,
    membership_id bigint NOT NULL,
    snapshot_id uuid NOT NULL,
    observed_at timestamptz NOT NULL,
    change_type text NOT NULL,
    CONSTRAINT ck_gtk_membership_observations_change_type
        CHECK (change_type IN ('opened', 'closed')),
    CONSTRAINT uq_gtk_membership_observation
        UNIQUE (membership_id, snapshot_id, change_type)
);

CREATE TABLE gtk_raw_snapshots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sync_run_id bigint,
    effective_at timestamptz,
    received_at timestamptz NOT NULL DEFAULT now(),
    payload_hash varchar(64) NOT NULL,
    is_complete boolean NOT NULL,
    payload jsonb NOT NULL,
    observed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE mileage_calculation_inputs (
    id bigserial PRIMARY KEY,
    run_id uuid NOT NULL,
    gtk_snapshot_id uuid,
    wialon_reading_id bigint,
    opening_balance_id uuid,
    gtk_membership_id bigint,
    CONSTRAINT ck_mileage_calculation_inputs_one_source
        CHECK (
            (gtk_snapshot_id IS NOT NULL)::int
            + (wialon_reading_id IS NOT NULL)::int
            + (opening_balance_id IS NOT NULL)::int
            + (gtk_membership_id IS NOT NULL)::int = 1
        )
);

CREATE TABLE mileage_calculation_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id uuid,
    algorithm_version varchar(32) NOT NULL,
    status text NOT NULL DEFAULT 'running',
    input_watermark jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    error text,
    CONSTRAINT ck_mileage_calculation_runs_status
        CHECK (status IN ('running', 'completed', 'partial', 'failed'))
);

CREATE TABLE wagon_idle_periods (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    wagon_asset_id uuid NOT NULL,
    aggregate_gtk_id bigint,
    period_from timestamptz NOT NULL,
    period_to timestamptz NOT NULL,
    status text NOT NULL,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_wagon_idle_period CHECK (period_to >= period_from),
    CONSTRAINT ck_wagon_idle_status
        CHECK (status IN ('confirmed', 'unknown_activity', 'estimated'))
);

CREATE TABLE wagon_mileage_ledger (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL,
    wagon_asset_id uuid NOT NULL,
    locomotive_asset_id uuid,
    train_gtk_id integer,
    period_from timestamptz NOT NULL,
    period_to timestamptz NOT NULL,
    km numeric(12, 2) NOT NULL,
    estimated boolean NOT NULL DEFAULT false,
    status text NOT NULL DEFAULT 'active',
    idempotency_key varchar(128) NOT NULL,
    calculation_details jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    classification varchar(16) NOT NULL DEFAULT 'HELD',
    calculation_eligible boolean NOT NULL DEFAULT false,
    CONSTRAINT ck_wagon_mileage_ledger_classification
        CHECK (classification IN ('CONFIRMED', 'ESTIMATED', 'HELD')),
    CONSTRAINT ck_wagon_mileage_ledger_nonnegative CHECK (km >= 0),
    CONSTRAINT ck_wagon_mileage_ledger_period CHECK (period_to >= period_from),
    CONSTRAINT ck_wagon_mileage_ledger_status
        CHECK (status IN ('active', 'superseded', 'rejected')),
    CONSTRAINT uq_wagon_mileage_ledger_idempotency UNIQUE (idempotency_key)
);

CREATE TABLE wagon_mileage_opening_balances (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id uuid NOT NULL,
    mileage_km numeric(12, 2) NOT NULL,
    effective_at timestamptz NOT NULL,
    created_by uuid,
    note text,
    created_at timestamptz NOT NULL DEFAULT now(),
    approved_by uuid,
    supersedes_id uuid,
    status varchar(16) NOT NULL DEFAULT 'pending',
    approved_at timestamptz,
    CONSTRAINT ck_wagon_mileage_opening_approval_audit
        CHECK (status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)),
    CONSTRAINT ck_wagon_mileage_opening_nonnegative CHECK (mileage_km >= 0),
    CONSTRAINT ck_wagon_mileage_opening_status
        CHECK (status IN ('pending', 'approved', 'rejected', 'superseded'))
);

CREATE TABLE wialon_odometer_readings (
    id bigserial PRIMARY KEY,
    asset_id uuid,
    source_unit_id text NOT NULL,
    odometer_km numeric(16, 2) NOT NULL,
    reading_at timestamptz,
    received_at timestamptz NOT NULL DEFAULT now(),
    accepted boolean NOT NULL,
    rejection_reason text,
    payload_hash varchar(64) NOT NULL,
    payload jsonb NOT NULL,
    calculation_eligible boolean NOT NULL DEFAULT false,
    classification varchar(16) NOT NULL DEFAULT 'HELD',
    measurement_key varchar(64),
    CONSTRAINT ck_wialon_odometer_classification
        CHECK (classification IN ('CONFIRMED', 'ESTIMATED', 'HELD')),
    CONSTRAINT ck_wialon_odometer_readings_nonnegative CHECK (odometer_km >= 0),
    CONSTRAINT uq_wialon_odometer_measurement_key UNIQUE (measurement_key),
    CONSTRAINT uq_wialon_odometer_readings_payload_hash UNIQUE (payload_hash)
);

CREATE TABLE wialon_raw_receipts (
    id bigserial PRIMARY KEY,
    source_unit_id text,
    asset_id uuid,
    reading_id bigint,
    transport varchar(8) NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    payload_hash varchar(64) NOT NULL,
    payload jsonb NOT NULL,
    CONSTRAINT ck_wialon_raw_receipts_transport CHECK (transport IN ('push', 'pull'))
);

CREATE INDEX ix_gtk_raw_snapshots_effective_received
    ON gtk_raw_snapshots (effective_at, received_at);
CREATE INDEX ix_gtk_raw_snapshots_payload_hash
    ON gtk_raw_snapshots (payload_hash);
CREATE INDEX ix_mileage_calculation_runs_started
    ON mileage_calculation_runs (started_at);
CREATE INDEX ix_wagon_idle_asset_period
    ON wagon_idle_periods (wagon_asset_id, period_from);
CREATE INDEX ix_wagon_mileage_ledger_asset_period
    ON wagon_mileage_ledger (wagon_asset_id, period_from, period_to);
CREATE INDEX ix_wagon_mileage_ledger_run
    ON wagon_mileage_ledger (run_id);
CREATE INDEX ix_wagon_mileage_opening_asset_effective
    ON wagon_mileage_opening_balances (asset_id, effective_at);
CREATE INDEX ix_wialon_odometer_asset_time
    ON wialon_odometer_readings (asset_id, reading_at);
CREATE INDEX ix_wialon_raw_receipts_received
    ON wialon_raw_receipts (received_at);
CREATE INDEX ix_wialon_raw_receipts_unit_received
    ON wialon_raw_receipts (source_unit_id, received_at);
CREATE UNIQUE INDEX uq_mileage_run_input_gtk_membership
    ON mileage_calculation_inputs (run_id, gtk_membership_id)
    WHERE gtk_membership_id IS NOT NULL;
CREATE UNIQUE INDEX uq_mileage_run_input_gtk_snapshot
    ON mileage_calculation_inputs (run_id, gtk_snapshot_id)
    WHERE gtk_snapshot_id IS NOT NULL;
CREATE UNIQUE INDEX uq_mileage_run_input_opening_balance
    ON mileage_calculation_inputs (run_id, opening_balance_id)
    WHERE opening_balance_id IS NOT NULL;
CREATE UNIQUE INDEX uq_mileage_run_input_wialon_reading
    ON mileage_calculation_inputs (run_id, wialon_reading_id)
    WHERE wialon_reading_id IS NOT NULL;
CREATE UNIQUE INDEX uq_wagon_mileage_opening_active_approved
    ON wagon_mileage_opening_balances (asset_id)
    WHERE status = 'approved';

ALTER TABLE gtk_membership_observations
    ADD CONSTRAINT gtk_membership_observations_membership_id_fkey
    FOREIGN KEY (membership_id) REFERENCES gtk_train_members(id) ON DELETE CASCADE;
ALTER TABLE gtk_membership_observations
    ADD CONSTRAINT gtk_membership_observations_snapshot_id_fkey
    FOREIGN KEY (snapshot_id) REFERENCES gtk_raw_snapshots(id) ON DELETE RESTRICT;
ALTER TABLE gtk_raw_snapshots
    ADD CONSTRAINT gtk_raw_snapshots_sync_run_id_fkey
    FOREIGN KEY (sync_run_id) REFERENCES gtk_sync_runs(id) ON DELETE SET NULL;
ALTER TABLE mileage_calculation_inputs
    ADD CONSTRAINT mileage_calculation_inputs_gtk_membership_id_fkey
    FOREIGN KEY (gtk_membership_id) REFERENCES gtk_train_members(id) ON DELETE RESTRICT;
ALTER TABLE mileage_calculation_inputs
    ADD CONSTRAINT mileage_calculation_inputs_gtk_snapshot_id_fkey
    FOREIGN KEY (gtk_snapshot_id) REFERENCES gtk_raw_snapshots(id) ON DELETE RESTRICT;
ALTER TABLE mileage_calculation_inputs
    ADD CONSTRAINT mileage_calculation_inputs_opening_balance_id_fkey
    FOREIGN KEY (opening_balance_id) REFERENCES wagon_mileage_opening_balances(id) ON DELETE RESTRICT;
ALTER TABLE mileage_calculation_inputs
    ADD CONSTRAINT mileage_calculation_inputs_run_id_fkey
    FOREIGN KEY (run_id) REFERENCES mileage_calculation_runs(id) ON DELETE RESTRICT;
ALTER TABLE mileage_calculation_inputs
    ADD CONSTRAINT mileage_calculation_inputs_wialon_reading_id_fkey
    FOREIGN KEY (wialon_reading_id) REFERENCES wialon_odometer_readings(id) ON DELETE RESTRICT;
ALTER TABLE mileage_calculation_runs
    ADD CONSTRAINT mileage_calculation_runs_snapshot_id_fkey
    FOREIGN KEY (snapshot_id) REFERENCES gtk_raw_snapshots(id) ON DELETE SET NULL;
ALTER TABLE wagon_idle_periods
    ADD CONSTRAINT wagon_idle_periods_wagon_asset_id_fkey
    FOREIGN KEY (wagon_asset_id) REFERENCES fixed_assets(id) ON DELETE RESTRICT;
ALTER TABLE wagon_mileage_ledger
    ADD CONSTRAINT wagon_mileage_ledger_locomotive_asset_id_fkey
    FOREIGN KEY (locomotive_asset_id) REFERENCES fixed_assets(id) ON DELETE RESTRICT;
ALTER TABLE wagon_mileage_ledger
    ADD CONSTRAINT wagon_mileage_ledger_run_id_fkey
    FOREIGN KEY (run_id) REFERENCES mileage_calculation_runs(id) ON DELETE RESTRICT;
ALTER TABLE wagon_mileage_ledger
    ADD CONSTRAINT wagon_mileage_ledger_wagon_asset_id_fkey
    FOREIGN KEY (wagon_asset_id) REFERENCES fixed_assets(id) ON DELETE RESTRICT;
ALTER TABLE wagon_mileage_opening_balances
    ADD CONSTRAINT wagon_mileage_opening_balances_approved_by_fkey
    FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE wagon_mileage_opening_balances
    ADD CONSTRAINT wagon_mileage_opening_balances_asset_id_fkey
    FOREIGN KEY (asset_id) REFERENCES fixed_assets(id) ON DELETE RESTRICT;
ALTER TABLE wagon_mileage_opening_balances
    ADD CONSTRAINT wagon_mileage_opening_balances_created_by_fkey
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE wagon_mileage_opening_balances
    ADD CONSTRAINT wagon_mileage_opening_balances_supersedes_id_fkey
    FOREIGN KEY (supersedes_id) REFERENCES wagon_mileage_opening_balances(id) ON DELETE RESTRICT;
ALTER TABLE wialon_odometer_readings
    ADD CONSTRAINT wialon_odometer_readings_asset_id_fkey
    FOREIGN KEY (asset_id) REFERENCES fixed_assets(id) ON DELETE RESTRICT;
ALTER TABLE wialon_raw_receipts
    ADD CONSTRAINT wialon_raw_receipts_asset_id_fkey
    FOREIGN KEY (asset_id) REFERENCES fixed_assets(id) ON DELETE SET NULL;
ALTER TABLE wialon_raw_receipts
    ADD CONSTRAINT wialon_raw_receipts_reading_id_fkey
    FOREIGN KEY (reading_id) REFERENCES wialon_odometer_readings(id) ON DELETE SET NULL;
