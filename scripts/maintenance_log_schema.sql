-- ═══════════════════════════════════════════════════════════════════════════════
-- Таблица истории обслуживания (maintenance_log)
-- Хранит данные о расходе ТМЦ по участкам
-- ═══════════════════════════════════════════════════════════════════════════════

-- Удаляем таблицу если нужно пересоздать
-- DROP TABLE IF EXISTS public.maintenance_log;

-- Создание таблицы
CREATE TABLE IF NOT EXISTS public.maintenance_log (
    id                text PRIMARY KEY,
    section_id        uuid REFERENCES public.sections(id) ON DELETE SET NULL,
    section_name      text NOT NULL,
    department_id     uuid REFERENCES public.departments(id) ON DELETE SET NULL,
    item_name         text NOT NULL,
    qty               numeric NOT NULL DEFAULT 0,
    unit              text NOT NULL DEFAULT 'шт.',
    equipment         text,
    work_type         text,
    maintenance_date  date,
    created_at        timestamptz NOT NULL DEFAULT now()
);

-- Комментарии
COMMENT ON TABLE public.maintenance_log IS 'История обслуживания и расхода ТМЦ по участкам';
COMMENT ON COLUMN public.maintenance_log.id IS 'Уникальный идентификатор записи';
COMMENT ON COLUMN public.maintenance_log.section_id IS 'ID участка из таблицы sections';
COMMENT ON COLUMN public.maintenance_log.section_name IS 'Название участка (ПТОВ, ВРП, ЭЛ_ДЕПО, ПТОЛ)';
COMMENT ON COLUMN public.maintenance_log.department_id IS 'ID подразделения из таблицы departments';
COMMENT ON COLUMN public.maintenance_log.item_name IS 'Наименование номенклатуры ТМЦ';
COMMENT ON COLUMN public.maintenance_log.qty IS 'Количество израсходованных единиц';
COMMENT ON COLUMN public.maintenance_log.unit IS 'Единица измерения';
COMMENT ON COLUMN public.maintenance_log.equipment IS 'Оборудование (локомотив/вагон)';
COMMENT ON COLUMN public.maintenance_log.work_type IS 'Вид работ (ТО-1, ТО-2, ТР и т.д.)';
COMMENT ON COLUMN public.maintenance_log.maintenance_date IS 'Дата обслуживания';

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_maintenance_log_section 
    ON public.maintenance_log(section_name);

CREATE INDEX IF NOT EXISTS idx_maintenance_log_section_id 
    ON public.maintenance_log(section_id);

CREATE INDEX IF NOT EXISTS idx_maintenance_log_department 
    ON public.maintenance_log(department_id);

CREATE INDEX IF NOT EXISTS idx_maintenance_log_item 
    ON public.maintenance_log(item_name);

CREATE INDEX IF NOT EXISTS idx_maintenance_log_date 
    ON public.maintenance_log(maintenance_date);

CREATE INDEX IF NOT EXISTS idx_maintenance_log_equipment 
    ON public.maintenance_log(equipment);

CREATE INDEX IF NOT EXISTS idx_maintenance_log_work_type 
    ON public.maintenance_log(work_type);

-- Составной индекс для анализа по участкам и позициям
CREATE INDEX IF NOT EXISTS idx_maintenance_log_section_item 
    ON public.maintenance_log(section_name, item_name);

-- ═══════════════════════════════════════════════════════════════════════════════
-- Row Level Security (RLS)
-- ═══════════════════════════════════════════════════════════════════════════════

ALTER TABLE public.maintenance_log ENABLE ROW LEVEL SECURITY;

-- Политика SELECT - все могут читать
DROP POLICY IF EXISTS "maintenance_log_select_policy" ON public.maintenance_log;
CREATE POLICY "maintenance_log_select_policy" ON public.maintenance_log
    FOR SELECT
    TO anon, authenticated
    USING (true);

-- Политика INSERT - все могут добавлять
DROP POLICY IF EXISTS "maintenance_log_insert_policy" ON public.maintenance_log;
CREATE POLICY "maintenance_log_insert_policy" ON public.maintenance_log
    FOR INSERT
    TO anon, authenticated
    WITH CHECK (true);

-- Политика UPDATE - все могут обновлять
DROP POLICY IF EXISTS "maintenance_log_update_policy" ON public.maintenance_log;
CREATE POLICY "maintenance_log_update_policy" ON public.maintenance_log
    FOR UPDATE
    TO anon, authenticated
    USING (true)
    WITH CHECK (true);

-- Политика DELETE - все могут удалять
DROP POLICY IF EXISTS "maintenance_log_delete_policy" ON public.maintenance_log;
CREATE POLICY "maintenance_log_delete_policy" ON public.maintenance_log
    FOR DELETE
    TO anon, authenticated
    USING (true);

-- ═══════════════════════════════════════════════════════════════════════════════
-- Полезные запросы для анализа
-- ═══════════════════════════════════════════════════════════════════════════════

-- Расход по участкам
-- SELECT section_name, COUNT(*) as records, SUM(qty) as total_qty
-- FROM maintenance_log
-- GROUP BY section_name
-- ORDER BY total_qty DESC;

-- Топ-10 позиций по расходу
-- SELECT item_name, SUM(qty) as total_qty, COUNT(*) as usage_count
-- FROM maintenance_log
-- GROUP BY item_name
-- ORDER BY total_qty DESC
-- LIMIT 10;

-- Сравнение расхода по участкам для конкретной позиции
-- SELECT section_name, AVG(qty) as avg_qty, STDDEV(qty) as std_qty
-- FROM maintenance_log
-- WHERE item_name LIKE '%Масло%'
-- GROUP BY section_name;

-- ═══════════════════════════════════════════════════════════════════════════════
-- Готово! Теперь можно запускать импорт:
-- python scripts/import_maintenance_history.py --files "путь/ПТОВ.xlsx" "путь/ВРП.xlsx"
-- ═══════════════════════════════════════════════════════════════════════════════
