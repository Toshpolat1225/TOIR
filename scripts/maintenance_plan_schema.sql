-- ═══════════════════════════════════════════════════════════════════════════════
-- MAINTENANCE PLAN TABLE - Автоматическое планирование ТО на основе пробега
-- ═══════════════════════════════════════════════════════════════════════════════

-- Создаём таблицу для хранения планов ТО
CREATE TABLE IF NOT EXISTS maintenance_plan (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id TEXT NOT NULL REFERENCES fixed_assets(id) ON DELETE CASCADE,
    asset_name TEXT NOT NULL,
    maintenance_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Scheduled' CHECK (status IN ('Scheduled', 'InProgress', 'Completed', 'Cancelled')),
    trigger_mileage INTEGER NOT NULL,
    scheduled_date DATE NOT NULL,
    completed_date DATE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES auth.users(id),
    
    -- Уникальный индекс для предотвращения дубликатов
    CONSTRAINT unique_maintenance_plan UNIQUE (asset_id, maintenance_type, trigger_mileage)
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_maintenance_plan_asset ON maintenance_plan(asset_id);
CREATE INDEX IF NOT EXISTS idx_maintenance_plan_status ON maintenance_plan(status);
CREATE INDEX IF NOT EXISTS idx_maintenance_plan_scheduled ON maintenance_plan(scheduled_date);
CREATE INDEX IF NOT EXISTS idx_maintenance_plan_type ON maintenance_plan(maintenance_type);

-- Триггер для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION update_maintenance_plan_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_maintenance_plan_updated ON maintenance_plan;
CREATE TRIGGER trigger_maintenance_plan_updated
    BEFORE UPDATE ON maintenance_plan
    FOR EACH ROW
    EXECUTE FUNCTION update_maintenance_plan_timestamp();

-- RLS политики
ALTER TABLE maintenance_plan ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow read maintenance_plan" ON maintenance_plan;
CREATE POLICY "Allow read maintenance_plan" ON maintenance_plan
    FOR SELECT USING (true);

DROP POLICY IF EXISTS "Allow insert maintenance_plan" ON maintenance_plan;
CREATE POLICY "Allow insert maintenance_plan" ON maintenance_plan
    FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "Allow update maintenance_plan" ON maintenance_plan;
CREATE POLICY "Allow update maintenance_plan" ON maintenance_plan
    FOR UPDATE USING (true);

-- ═══════════════════════════════════════════════════════════════════════════════
-- VIEW: Активные планы ТО с информацией об агрегатах
-- ═══════════════════════════════════════════════════════════════════════════════

DROP VIEW IF EXISTS active_maintenance_plans;
CREATE VIEW active_maintenance_plans AS
SELECT 
    mp.id,
    mp.asset_id,
    mp.asset_name,
    mp.maintenance_type,
    mp.status,
    mp.trigger_mileage,
    mp.scheduled_date,
    mp.created_at,
    fa.mileage::INTEGER as current_mileage,
    fa.wialon_online,
    fa.asset_type,
    fa.series,
    (mp.trigger_mileage - COALESCE(fa.mileage::INTEGER, 0)) as remaining_km,
    CASE 
        WHEN (mp.trigger_mileage - COALESCE(fa.mileage::INTEGER, 0)) <= 0 THEN 'overdue'
        WHEN (mp.trigger_mileage - COALESCE(fa.mileage::INTEGER, 0)) <= 500 THEN 'critical'
        WHEN (mp.trigger_mileage - COALESCE(fa.mileage::INTEGER, 0)) <= 1000 THEN 'warning'
        ELSE 'normal'
    END as urgency
FROM maintenance_plan mp
JOIN fixed_assets fa ON mp.asset_id = fa.id
WHERE mp.status IN ('Scheduled', 'InProgress')
ORDER BY remaining_km ASC;

-- ═══════════════════════════════════════════════════════════════════════════════
-- FUNCTION: Автоматическое создание плана ТО при достижении порога
-- ═══════════════════════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION auto_schedule_maintenance()
RETURNS TRIGGER AS $$
DECLARE
    v_threshold INTEGER;
    v_maintenance_type TEXT;
    v_cycle_number INTEGER;
    v_next_threshold INTEGER;
    v_remaining_km INTEGER;
    v_scheduled_date DATE;
    v_thresholds INTEGER[] := ARRAY[5000, 15000, 30000, 100000, 200000, 400000, 800000, 1600000];
    v_types TEXT[] := ARRAY['ТО-1', 'ТО-2', 'ТО-3', 'ТР-1', 'ТР-2', 'ТР-3', 'СР', 'КР'];
BEGIN
    -- Проверяем только локомотивы и тепловозы
    IF NEW.asset_type NOT IN ('locomotive', 'diesel') THEN
        RETURN NEW;
    END IF;
    
    -- Проверяем только если пробег изменился
    IF OLD.mileage IS NOT DISTINCT FROM NEW.mileage THEN
        RETURN NEW;
    END IF;
    
    -- Проходим по всем порогам ТО
    FOR i IN 1..array_length(v_thresholds, 1) LOOP
        v_threshold := v_thresholds[i];
        v_maintenance_type := v_types[i];
        
        -- Вычисляем номер цикла и следующий порог
        v_cycle_number := FLOOR(COALESCE(NEW.mileage::INTEGER, 0) / v_threshold);
        v_next_threshold := (v_cycle_number + 1) * v_threshold;
        v_remaining_km := v_next_threshold - COALESCE(NEW.mileage::INTEGER, 0);
        
        -- Если осталось менее 10% до порога, создаём план
        IF v_remaining_km <= v_threshold * 0.1 THEN
            -- Рассчитываем дату (примерно 200 км/день)
            v_scheduled_date := CURRENT_DATE + GREATEST(0, CEIL(v_remaining_km / 200.0))::INTEGER;
            
            -- Создаём или обновляем план (upsert)
            INSERT INTO maintenance_plan (
                asset_id, 
                asset_name, 
                maintenance_type, 
                status, 
                trigger_mileage, 
                scheduled_date
            )
            VALUES (
                NEW.id,
                NEW.name,
                v_maintenance_type,
                'Scheduled',
                v_next_threshold,
                v_scheduled_date
            )
            ON CONFLICT (asset_id, maintenance_type, trigger_mileage) 
            DO UPDATE SET 
                scheduled_date = EXCLUDED.scheduled_date,
                updated_at = NOW()
            WHERE maintenance_plan.status = 'Scheduled';
            
            -- Обрабатываем только ближайший порог
            EXIT;
        END IF;
    END LOOP;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер для автоматического планирования при изменении пробега
DROP TRIGGER IF EXISTS trigger_auto_schedule_maintenance ON fixed_assets;
CREATE TRIGGER trigger_auto_schedule_maintenance
    AFTER UPDATE OF mileage ON fixed_assets
    FOR EACH ROW
    EXECUTE FUNCTION auto_schedule_maintenance();

-- ═══════════════════════════════════════════════════════════════════════════════
-- ТЕСТОВЫЕ ДАННЫЕ (опционально)
-- ═══════════════════════════════════════════════════════════════════════════════

-- Добавляем тестовые планы для существующих агрегатов с пробегом
INSERT INTO maintenance_plan (asset_id, asset_name, maintenance_type, status, trigger_mileage, scheduled_date)
SELECT 
    fa.id,
    fa.name,
    'ТО-1',
    'Scheduled',
    CEIL(COALESCE(fa.mileage::INTEGER, 0) / 5000.0) * 5000,
    CURRENT_DATE + 7
FROM fixed_assets fa
WHERE fa.asset_type IN ('locomotive', 'diesel')
  AND COALESCE(fa.mileage::INTEGER, 0) > 0
  AND NOT EXISTS (
      SELECT 1 FROM maintenance_plan mp 
      WHERE mp.asset_id = fa.id 
        AND mp.maintenance_type = 'ТО-1'
        AND mp.status = 'Scheduled'
  )
ON CONFLICT (asset_id, maintenance_type, trigger_mileage) DO NOTHING;

-- Выводим созданные планы
SELECT 
    asset_name,
    maintenance_type,
    status,
    trigger_mileage,
    scheduled_date
FROM maintenance_plan
ORDER BY scheduled_date;
