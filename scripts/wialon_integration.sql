-- ═══════════════════════════════════════════════════════════════════
-- ИНТЕГРАЦИЯ С WIALON
-- Добавляет поля для синхронизации пробегов из Wialon
-- Выполните этот скрипт в Supabase SQL Editor
-- ═══════════════════════════════════════════════════════════════════

-- 1. Добавляем поля Wialon в таблицу fixed_assets
ALTER TABLE fixed_assets 
ADD COLUMN IF NOT EXISTS wialon_id INTEGER,
ADD COLUMN IF NOT EXISTS wialon_last_sync TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS wialon_speed NUMERIC DEFAULT 0,
ADD COLUMN IF NOT EXISTS wialon_online BOOLEAN DEFAULT FALSE;

-- 2. Индекс для быстрого поиска по wialon_id
CREATE INDEX IF NOT EXISTS idx_fixed_assets_wialon_id 
ON fixed_assets(wialon_id) 
WHERE wialon_id IS NOT NULL;

-- 3. Таблица для хранения настроек интеграции
CREATE TABLE IF NOT EXISTS wialon_settings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  host TEXT NOT NULL DEFAULT 'https://hst-api.wialon.com',
  token TEXT,
  sync_interval_minutes INTEGER DEFAULT 5,
  auto_sync_enabled BOOLEAN DEFAULT FALSE,
  last_sync_at TIMESTAMPTZ,
  last_sync_status TEXT,
  last_sync_count INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Таблица истории пробегов (для аналитики)
-- Примечание: asset_id имеет тип TEXT, т.к. fixed_assets.id тоже TEXT
CREATE TABLE IF NOT EXISTS mileage_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id TEXT REFERENCES fixed_assets(id) ON DELETE CASCADE,
  mileage INTEGER NOT NULL,
  source TEXT DEFAULT 'wialon',
  recorded_at TIMESTAMPTZ DEFAULT NOW()
);

-- Индекс для быстрого поиска истории
CREATE INDEX IF NOT EXISTS idx_mileage_history_asset_date 
ON mileage_history(asset_id, recorded_at DESC);

-- 5. Таблица нормативов ТО по пробегу
CREATE TABLE IF NOT EXISTS maintenance_intervals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  interval_km INTEGER NOT NULL,
  interval_days INTEGER,
  asset_types TEXT[] DEFAULT ARRAY['locomotive', 'diesel'],
  description TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Заполняем нормативы ТО (значения по умолчанию, можно изменить через интерфейс)
-- ВАЖНО: interval_km можно настроить под ваши нужды (например, ТО-2 каждые 90 км)
INSERT INTO maintenance_intervals (code, name, interval_km, interval_days, description) VALUES
  ('ТО-1', 'Техническое обслуживание 1', 50, 7, 'Еженедельное ТО'),
  ('ТО-2', 'Техническое обслуживание 2', 90, 14, 'Двухнедельное ТО'),
  ('ТО-3', 'Техническое обслуживание 3', 200, 30, 'Ежемесячное ТО'),
  ('ТР-1', 'Текущий ремонт 1', 500, 90, 'Квартальный текущий ремонт'),
  ('ТР-2', 'Текущий ремонт 2', 1000, 180, 'Полугодовой ремонт'),
  ('ТР-3', 'Текущий ремонт 3', 2000, 365, 'Годовой ремонт'),
  ('СР', 'Средний ремонт', 5000, NULL, 'Средний ремонт локомотива'),
  ('КР', 'Капитальный ремонт', 10000, NULL, 'Полный капитальный ремонт')
ON CONFLICT (code) DO NOTHING;

-- 6. Удаляем старый объект maintenance_schedule если он существует (таблица или view)
DROP TABLE IF EXISTS maintenance_schedule CASCADE;
DROP VIEW IF EXISTS maintenance_schedule CASCADE;

-- 7. Создаём View для расчёта графика ТО
CREATE VIEW maintenance_schedule AS
WITH last_maintenance AS (
  SELECT 
    wo.unit,
    wo.repair_kind,
    MAX(wo.closed) as last_date,
    MAX(CAST(NULLIF(fa.mileage, '') AS INTEGER)) as mileage_at_maintenance
  FROM work_orders wo
  LEFT JOIN fixed_assets fa ON fa.name = wo.unit
  WHERE wo.status = 'completed'
    AND wo.repair_kind IN (SELECT code FROM maintenance_intervals)
  GROUP BY wo.unit, wo.repair_kind
),
asset_maintenance AS (
  SELECT 
    fa.id as asset_id,
    fa.name as asset_name,
    fa.asset_type,
    fa.series,
    COALESCE(CAST(NULLIF(fa.mileage, '') AS INTEGER), 0) as current_mileage,
    fa.wialon_online,
    fa.wialon_last_sync,
    mi.code as maintenance_type,
    mi.name as maintenance_name,
    mi.interval_km,
    mi.interval_days,
    lm.last_date as last_maintenance_date,
    lm.mileage_at_maintenance
  FROM fixed_assets fa
  CROSS JOIN maintenance_intervals mi
  LEFT JOIN last_maintenance lm ON lm.unit = fa.name AND lm.repair_kind = mi.code
  WHERE fa.asset_type IN ('locomotive', 'diesel')
    AND mi.is_active = TRUE
)
SELECT 
  asset_id,
  asset_name,
  asset_type,
  series,
  current_mileage,
  wialon_online,
  wialon_last_sync,
  maintenance_type,
  maintenance_name,
  interval_km,
  last_maintenance_date,
  COALESCE(mileage_at_maintenance, 0) + interval_km as due_mileage,
  (COALESCE(mileage_at_maintenance, 0) + interval_km) - current_mileage as remaining_km,
  CASE 
    WHEN (COALESCE(mileage_at_maintenance, 0) + interval_km) - current_mileage <= 0 THEN 'overdue'
    WHEN (COALESCE(mileage_at_maintenance, 0) + interval_km) - current_mileage <= interval_km * 0.1 THEN 'due'
    ELSE 'upcoming'
  END as status,
  CASE 
    WHEN (COALESCE(mileage_at_maintenance, 0) + interval_km) - current_mileage <= 0 THEN 'critical'
    WHEN (COALESCE(mileage_at_maintenance, 0) + interval_km) - current_mileage <= interval_km * 0.1 THEN 'high'
    WHEN (COALESCE(mileage_at_maintenance, 0) + interval_km) - current_mileage <= interval_km * 0.2 THEN 'medium'
    ELSE 'low'
  END as priority,
  CASE 
    WHEN (COALESCE(mileage_at_maintenance, 0) + interval_km) - current_mileage > 0 
    THEN CURRENT_DATE + ((COALESCE(mileage_at_maintenance, 0) + interval_km) - current_mileage) / 200
    ELSE CURRENT_DATE
  END as estimated_due_date
FROM asset_maintenance
ORDER BY 
  CASE 
    WHEN (COALESCE(mileage_at_maintenance, 0) + interval_km) - current_mileage <= 0 THEN 0
    WHEN (COALESCE(mileage_at_maintenance, 0) + interval_km) - current_mileage <= interval_km * 0.1 THEN 1
    WHEN (COALESCE(mileage_at_maintenance, 0) + interval_km) - current_mileage <= interval_km * 0.2 THEN 2
    ELSE 3
  END,
  (COALESCE(mileage_at_maintenance, 0) + interval_km) - current_mileage;

-- 8. Функция для записи истории пробега
CREATE OR REPLACE FUNCTION record_mileage_change()
RETURNS TRIGGER AS $$
BEGIN
  IF OLD.mileage IS DISTINCT FROM NEW.mileage AND NEW.mileage IS NOT NULL AND NEW.mileage != '' THEN
    INSERT INTO mileage_history (asset_id, mileage, source)
    VALUES (NEW.id, CAST(NEW.mileage AS INTEGER), 
      CASE WHEN NEW.wialon_last_sync > OLD.wialon_last_sync THEN 'wialon' ELSE 'manual' END
    );
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 9. Триггер для автоматической записи истории
DROP TRIGGER IF EXISTS trigger_mileage_history ON fixed_assets;
CREATE TRIGGER trigger_mileage_history
AFTER UPDATE ON fixed_assets
FOR EACH ROW
EXECUTE FUNCTION record_mileage_change();

-- 10. RLS политики
ALTER TABLE wialon_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE mileage_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE maintenance_intervals ENABLE ROW LEVEL SECURITY;

-- Удаляем старые политики если есть
DROP POLICY IF EXISTS "wialon_settings_select" ON wialon_settings;
DROP POLICY IF EXISTS "wialon_settings_all" ON wialon_settings;
DROP POLICY IF EXISTS "mileage_history_select" ON mileage_history;
DROP POLICY IF EXISTS "mileage_history_insert" ON mileage_history;
DROP POLICY IF EXISTS "maintenance_intervals_select" ON maintenance_intervals;
DROP POLICY IF EXISTS "maintenance_intervals_admin" ON maintenance_intervals;

-- Создаём политики
CREATE POLICY "wialon_settings_select" ON wialon_settings FOR SELECT USING (true);
CREATE POLICY "wialon_settings_all" ON wialon_settings FOR ALL USING (true);

CREATE POLICY "mileage_history_select" ON mileage_history FOR SELECT USING (true);
CREATE POLICY "mileage_history_insert" ON mileage_history FOR INSERT WITH CHECK (true);

CREATE POLICY "maintenance_intervals_select" ON maintenance_intervals FOR SELECT USING (true);
CREATE POLICY "maintenance_intervals_all" ON maintenance_intervals FOR ALL USING (true);

-- 11. Проверка результатов
SELECT 'Wialon интеграция настроена успешно!' as status;

SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'fixed_assets' 
AND column_name LIKE 'wialon%';
