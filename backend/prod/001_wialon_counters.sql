-- PROD migratsiya (faqat 2 ta YANGI jadval qo'shadi; mavjud jadvallarga tegmaydi).
BEGIN;
CREATE TABLE IF NOT EXISTS wialon_counter_state (
    asset_id          uuid PRIMARY KEY REFERENCES fixed_assets(id) ON DELETE CASCADE,
    baseline_cnm      numeric(16,2),
    last_cnm          numeric(16,2),
    last_cnm_at       timestamptz,
    baseline_cneh     numeric(14,3),
    last_cneh         numeric(14,3),
    last_cneh_at      timestamptz,
    engine_hours      numeric(12,3),
    suspect_absolute  boolean NOT NULL DEFAULT false,
    last_status       text,
    last_reason       text,
    updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS wialon_rejected_readings (
    id             bigserial PRIMARY KEY,
    asset_id       uuid NOT NULL REFERENCES fixed_assets(id) ON DELETE CASCADE,
    counter        text NOT NULL CONSTRAINT wialon_rejected_counter_check CHECK (counter IN ('mileage','engine_hours')),
    value          numeric(18,3),
    previous_value numeric(18,3),
    reading_at     timestamptz,
    reason         text NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_wialon_rejected_asset_time ON wialon_rejected_readings (asset_id, created_at DESC);
COMMIT;
