-- ═══════════════════════════════════════════════════════════════════════════════
-- Таблица нормативов расхода ТМЦ (nomenclature_norms)
-- Хранит нормативы расхода для каждого участка и вида работ
-- ═══════════════════════════════════════════════════════════════════════════════

-- Удаляем таблицу если нужно пересоздать
DROP TABLE IF EXISTS public.nomenclature_norms CASCADE;

CREATE TABLE public.nomenclature_norms (
    id                  text PRIMARY KEY,
    nomenclature_id     text NOT NULL,                      -- ID из таблицы nomenclature
    department_id       text NOT NULL,                      -- ID из таблицы departments
    work_type           text NOT NULL DEFAULT '',           -- Вид работ (ТО-1, ТО-2, ТР и т.д.)
    standard_quantity   numeric NOT NULL DEFAULT 1,         -- Нормативное количество
    unit                text NOT NULL DEFAULT 'шт.',        -- Единица измерения
    avg_price           numeric NOT NULL DEFAULT 0,         -- Средняя цена за единицу (сум)
    min_quantity        numeric DEFAULT 0,                  -- Минимальное количество
    max_quantity        numeric DEFAULT NULL,               -- Максимальное количество
    note                text DEFAULT '',                    -- Примечание
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    
    UNIQUE(nomenclature_id, department_id, work_type)
);

-- Комментарии
COMMENT ON TABLE public.nomenclature_norms IS 'Нормативы расхода ТМЦ по участкам и видам работ';
COMMENT ON COLUMN public.nomenclature_norms.nomenclature_id IS 'ID позиции из справочника nomenclature';
COMMENT ON COLUMN public.nomenclature_norms.department_id IS 'ID участка (ПТОВ, ВРП, ЭЛ_ДЕПО, ПТОЛ)';
COMMENT ON COLUMN public.nomenclature_norms.work_type IS 'Вид работ (ТО-1, ТО-2, ТР-1 и т.д.)';
COMMENT ON COLUMN public.nomenclature_norms.standard_quantity IS 'Нормативное количество на один ремонт';
COMMENT ON COLUMN public.nomenclature_norms.avg_price IS 'Средняя цена за единицу (сум)';

-- Индексы
CREATE INDEX IF NOT EXISTS idx_norms_department ON public.nomenclature_norms(department_id);
CREATE INDEX IF NOT EXISTS idx_norms_nomenclature ON public.nomenclature_norms(nomenclature_id);
CREATE INDEX IF NOT EXISTS idx_norms_work_type ON public.nomenclature_norms(work_type);
CREATE INDEX IF NOT EXISTS idx_norms_dept_work ON public.nomenclature_norms(department_id, work_type);

-- RLS
ALTER TABLE public.nomenclature_norms ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "norms_select" ON public.nomenclature_norms;
CREATE POLICY "norms_select" ON public.nomenclature_norms
    FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "norms_insert" ON public.nomenclature_norms;
CREATE POLICY "norms_insert" ON public.nomenclature_norms
    FOR INSERT TO anon, authenticated WITH CHECK (true);

DROP POLICY IF EXISTS "norms_update" ON public.nomenclature_norms;
CREATE POLICY "norms_update" ON public.nomenclature_norms
    FOR UPDATE TO anon, authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "norms_delete" ON public.nomenclature_norms;
CREATE POLICY "norms_delete" ON public.nomenclature_norms
    FOR DELETE TO anon, authenticated USING (true);

-- ═══════════════════════════════════════════════════════════════════════════════
-- Шаблоны ТМЦ для видов работ (work_type_templates)
-- Автоматически добавляемые позиции при выборе вида работ
-- ═══════════════════════════════════════════════════════════════════════════════

DROP TABLE IF EXISTS public.work_type_templates CASCADE;

CREATE TABLE public.work_type_templates (
    id                  text PRIMARY KEY,
    work_type           text NOT NULL,                      -- Вид работ (ТО-2, ПТОЛ ТО-2)
    department_id       text NOT NULL,                      -- ID из таблицы departments
    nomenclature_id     text NOT NULL,                      -- ID из таблицы nomenclature
    default_quantity    numeric NOT NULL DEFAULT 1,         -- Количество по умолчанию
    is_required         boolean NOT NULL DEFAULT false,     -- Обязательная позиция
    sort_order          int NOT NULL DEFAULT 0,
    created_at          timestamptz NOT NULL DEFAULT now(),
    
    UNIQUE(work_type, department_id, nomenclature_id)
);

COMMENT ON TABLE public.work_type_templates IS 'Шаблоны ТМЦ для автозаполнения по виду работ';

-- Индексы
CREATE INDEX IF NOT EXISTS idx_templates_work_type ON public.work_type_templates(work_type);
CREATE INDEX IF NOT EXISTS idx_templates_department ON public.work_type_templates(department_id);

-- RLS
ALTER TABLE public.work_type_templates ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "templates_select" ON public.work_type_templates;
CREATE POLICY "templates_select" ON public.work_type_templates
    FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "templates_insert" ON public.work_type_templates;
CREATE POLICY "templates_insert" ON public.work_type_templates
    FOR INSERT TO anon, authenticated WITH CHECK (true);

DROP POLICY IF EXISTS "templates_update" ON public.work_type_templates;
CREATE POLICY "templates_update" ON public.work_type_templates
    FOR UPDATE TO anon, authenticated USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "templates_delete" ON public.work_type_templates;
CREATE POLICY "templates_delete" ON public.work_type_templates
    FOR DELETE TO anon, authenticated USING (true);

-- ═══════════════════════════════════════════════════════════════════════════════
-- Пример данных для ПТОЛ ТО-2
-- ═══════════════════════════════════════════════════════════════════════════════

-- INSERT INTO public.nomenclature_norms (nomenclature_id, department_id, work_type, standard_quantity, avg_price)
-- SELECT 
--     n.id,
--     d.id,
--     'ТО-2',
--     2,
--     50000
-- FROM public.nomenclature n
-- CROSS JOIN public.departments d
-- WHERE n.name LIKE '%Масло%' AND d.name = 'ПТОЛ'
-- ON CONFLICT DO NOTHING;
