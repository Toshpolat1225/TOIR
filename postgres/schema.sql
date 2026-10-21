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
INSERT INTO fixed_asset_types(code) VALUES ('locomotive'), ('diesel'), ('wagon');

CREATE TABLE fixed_asset_statuses (
    code       text PRIMARY KEY,
    is_active  boolean NOT NULL DEFAULT true,
    behavior   text NOT NULL DEFAULT 'operational' CHECK (behavior IN ('operational','maintenance','repair','out_of_service')),
    color      text NOT NULL DEFAULT 'green' CHECK (color IN ('blue','green','amber','orange','red','gray','purple'))
);
INSERT INTO fixed_asset_statuses(code)
VALUES ('operational'), ('maintenance'), ('repair'), ('out_of_service');
UPDATE fixed_asset_statuses SET behavior = code, color = CASE code WHEN 'operational' THEN 'green' WHEN 'maintenance' THEN 'amber' WHEN 'repair' THEN 'orange' ELSE 'gray' END;

CREATE TABLE fixed_assets (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    inv_number           text NOT NULL UNIQUE,
    name                 text NOT NULL,
    asset_type           text NOT NULL REFERENCES fixed_asset_types(code) ON UPDATE CASCADE ON DELETE RESTRICT,
    series               text,
    depot                text,
    section_id           uuid REFERENCES sections(id) ON DELETE SET NULL,
    status               text NOT NULL DEFAULT 'operational'
                         REFERENCES fixed_asset_statuses(code) ON UPDATE CASCADE ON DELETE RESTRICT,
    comm_date            date,
    year_built           integer,
    mileage              numeric(12,2) NOT NULL DEFAULT 0,
    last_maint_date      date,
    next_maint_date      date,
    initial_cost         numeric(16,2),
    owner                text,
    -- Wialon
    wialon_id            varchar(100) UNIQUE,
    wialon_last_sync     timestamptz,
    wialon_speed         numeric(6,2),
    wialon_online        boolean NOT NULL DEFAULT false,
    -- ML natijalari
    failure_probability  numeric(5,4),
    health_score         numeric(5,2),
    predicted_failure_km numeric(12,2),
    last_ml_update       timestamptz,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_assets_type_status ON fixed_assets(asset_type, status);
CREATE INDEX ix_assets_section     ON fixed_assets(section_id);
CREATE INDEX ix_assets_series      ON fixed_assets(series);

CREATE TABLE mileage_history (
    id           bigserial PRIMARY KEY,
    asset_id     uuid NOT NULL REFERENCES fixed_assets(id) ON DELETE CASCADE,
    mileage      numeric(12,2) NOT NULL,
    source       text NOT NULL DEFAULT 'wialon' CHECK (source IN ('wialon','manual')),
    recorded_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_mileage_asset_time ON mileage_history(asset_id, recorded_at DESC);

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
    locale text NOT NULL CHECK (locale IN ('uz-Latn','uz-Cyrl','ru')),
    name text NOT NULL,
    CONSTRAINT uq_department_translation_locale UNIQUE (department_id, locale)
);
CREATE TABLE section_translations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    section_id uuid NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    locale text NOT NULL CHECK (locale IN ('uz-Latn','uz-Cyrl','ru')),
    name text NOT NULL,
    CONSTRAINT uq_section_translation_locale UNIQUE (section_id, locale)
);
CREATE TABLE work_type_translations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    work_type_id uuid NOT NULL REFERENCES work_types(id) ON DELETE CASCADE,
    locale text NOT NULL CHECK (locale IN ('uz-Latn','uz-Cyrl','ru')),
    name text NOT NULL,
    CONSTRAINT uq_work_type_translation_locale UNIQUE (work_type_id, locale)
);
CREATE TABLE work_subtask_translations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    work_subtask_id uuid NOT NULL REFERENCES work_subtasks(id) ON DELETE CASCADE,
    locale text NOT NULL CHECK (locale IN ('uz-Latn','uz-Cyrl','ru')),
    name text NOT NULL,
    CONSTRAINT uq_work_subtask_translation_locale UNIQUE (work_subtask_id, locale)
);
CREATE TABLE nomenclature_translations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    nomenclature_id uuid NOT NULL REFERENCES nomenclature(id) ON DELETE CASCADE,
    locale text NOT NULL CHECK (locale IN ('uz-Latn','uz-Cyrl','ru')),
    name text NOT NULL,
    CONSTRAINT uq_nomenclature_translation_locale UNIQUE (nomenclature_id, locale)
);
CREATE TABLE fixed_asset_type_translations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    type_code text NOT NULL REFERENCES fixed_asset_types(code) ON DELETE CASCADE,
    locale text NOT NULL CHECK (locale IN ('uz-Latn','uz-Cyrl','ru')),
    name text NOT NULL,
    CONSTRAINT uq_fixed_asset_type_translation_locale UNIQUE (type_code, locale)
);
CREATE TABLE fixed_asset_status_translations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    status_code text NOT NULL REFERENCES fixed_asset_statuses(code) ON DELETE CASCADE,
    locale text NOT NULL CHECK (locale IN ('uz-Latn','uz-Cyrl','ru')),
    name text NOT NULL,
    CONSTRAINT uq_fixed_asset_status_translation_locale UNIQUE (status_code, locale)
);
CREATE UNIQUE INDEX uq_fixed_asset_type_translation_name ON fixed_asset_type_translations(locale, lower(name));
CREATE UNIQUE INDEX uq_fixed_asset_status_translation_name ON fixed_asset_status_translations(locale, lower(name));

INSERT INTO fixed_asset_type_translations(type_code, locale, name) VALUES
    ('locomotive', 'ru', 'Локомотив'), ('locomotive', 'uz-Latn', 'Lokomotiv'), ('locomotive', 'uz-Cyrl', 'Локомотив'),
    ('diesel', 'ru', 'Тепловоз'), ('diesel', 'uz-Latn', 'Teplovoz'), ('diesel', 'uz-Cyrl', 'Тепловоз'),
    ('wagon', 'ru', 'Вагон'), ('wagon', 'uz-Latn', 'Vagon'), ('wagon', 'uz-Cyrl', 'Вагон');
INSERT INTO fixed_asset_status_translations(status_code, locale, name) VALUES
    ('operational', 'ru', 'В эксплуатации'), ('operational', 'uz-Latn', 'Foydalanishda'), ('operational', 'uz-Cyrl', 'Фойдаланишда'),
    ('maintenance', 'ru', 'На ТО'), ('maintenance', 'uz-Latn', 'Texnik xizmatda'), ('maintenance', 'uz-Cyrl', 'Техник хизматда'),
    ('repair', 'ru', 'Ремонт'), ('repair', 'uz-Latn', 'Ta’mirda'), ('repair', 'uz-Cyrl', 'Таъмирда'),
    ('out_of_service', 'ru', 'Выведен'), ('out_of_service', 'uz-Latn', 'Foydalanishdan chiqarilgan'), ('out_of_service', 'uz-Cyrl', 'Фойдаланишдан чиқарилган');

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

-- =====================================================================
-- Keyingi bosqich (alohida migratsiya): analytics view'lari
--   executive_summary, section_efficiency, work_type_efficiency,
--   monthly_efficiency, fleet_health, ai_insights_summary,
--   maintenance_schedule, work_order_tmc_details
-- ТО-reja yaratish (auto_schedule_maintenance) — backend servis qatlamida.
-- =====================================================================
