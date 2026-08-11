-- Добавление полей для отслеживания пробега в нарядах
-- Это позволяет системе понимать, на каком цикле ТО был создан наряд

-- Добавляем колонку для пробега на момент создания наряда
ALTER TABLE work_orders 
ADD COLUMN IF NOT EXISTS mileage_at_creation INTEGER;

-- Добавляем колонку для порога пробега (следующее ТО)
-- Это позволяет отслеживать конкретный цикл ТО
ALTER TABLE work_orders 
ADD COLUMN IF NOT EXISTS mileage_threshold INTEGER;

-- Комментарии к колонкам
COMMENT ON COLUMN work_orders.mileage_at_creation IS 'Пробег оборудования на момент создания наряда (км)';
COMMENT ON COLUMN work_orders.mileage_threshold IS 'Порог пробега для данного ТО (км). Используется для определения цикла ТО';

-- Индекс для быстрого поиска нарядов по оборудованию и типу ремонта
CREATE INDEX IF NOT EXISTS idx_work_orders_unit_repair 
ON work_orders(unit, repair_kind);

-- Индекс для поиска активных нарядов
CREATE INDEX IF NOT EXISTS idx_work_orders_active 
ON work_orders(status) 
WHERE status IN ('pending', 'in_progress');

-- Представление для активных ТО нарядов с данными пробега
CREATE OR REPLACE VIEW active_maintenance_orders AS
SELECT 
    wo.id,
    wo.unit,
    wo.repair_kind,
    wo.status,
    wo.mileage_at_creation,
    wo.mileage_threshold,
    wo.created,
    wo.section,
    wo.priority,
    fa.mileage as current_mileage,
    fa.wialon_online,
    fa.wialon_last_sync,
    CASE 
        WHEN fa.mileage IS NOT NULL AND wo.mileage_threshold IS NOT NULL 
        THEN wo.mileage_threshold - CAST(fa.mileage AS INTEGER)
        ELSE NULL 
    END as remaining_km
FROM work_orders wo
LEFT JOIN fixed_assets fa ON fa.name = wo.unit
WHERE wo.status IN ('pending', 'in_progress')
  AND wo.repair_kind IN ('ТО-1', 'ТО-2', 'ТО-3', 'ТР-1', 'ТР-2', 'ТР-3', 'СР', 'КР');
