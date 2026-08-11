-- ═══════════════════════════════════════════════════════════════════
-- ИНДЕКСЫ ДЛЯ ОПТИМИЗАЦИИ СТРАНИЦЫ АНАЛИТИКИ
-- Выполните этот скрипт в Supabase SQL Editor для ускорения запросов
-- ═══════════════════════════════════════════════════════════════════

-- ═══════════════════════════════════════════════════════════════════
-- 1. ИНДЕКСЫ ДЛЯ ТАБЛИЦЫ fixed_assets (основная таблица)
-- ═══════════════════════════════════════════════════════════════════

-- Ускоряет фильтрацию по типу оборудования (locomotive/wagon/diesel)
CREATE INDEX IF NOT EXISTS idx_fixed_assets_asset_type 
ON fixed_assets(asset_type);

-- Ускоряет фильтрацию по серии
CREATE INDEX IF NOT EXISTS idx_fixed_assets_series 
ON fixed_assets(series);

-- Ускоряет фильтрацию по депо
CREATE INDEX IF NOT EXISTS idx_fixed_assets_depot 
ON fixed_assets(depot);

-- Ускоряет фильтрацию по статусу
CREATE INDEX IF NOT EXISTS idx_fixed_assets_status 
ON fixed_assets(status);

-- Составной индекс для частых запросов
CREATE INDEX IF NOT EXISTS idx_fixed_assets_type_status 
ON fixed_assets(asset_type, status);


-- ═══════════════════════════════════════════════════════════════════
-- 2. ИНДЕКСЫ ДЛЯ ТАБЛИЦЫ work_orders
-- ═══════════════════════════════════════════════════════════════════

-- Ускоряет сортировку по дате создания
CREATE INDEX IF NOT EXISTS idx_work_orders_created_at 
ON work_orders(created_at DESC);

-- Ускоряет фильтрацию по статусу
CREATE INDEX IF NOT EXISTS idx_work_orders_status 
ON work_orders(status);

-- Ускоряет фильтрацию по section (участок)
CREATE INDEX IF NOT EXISTS idx_work_orders_section 
ON work_orders(section);

-- Ускоряет фильтрацию по depot (депо)
CREATE INDEX IF NOT EXISTS idx_work_orders_depot 
ON work_orders(depot);

-- Ускоряет фильтрацию по unit (оборудование)
CREATE INDEX IF NOT EXISTS idx_work_orders_unit 
ON work_orders(unit);

-- Составной индекс для аналитики
CREATE INDEX IF NOT EXISTS idx_work_orders_analytics 
ON work_orders(section, status, created_at DESC);


-- ═══════════════════════════════════════════════════════════════════
-- 3. ИНДЕКСЫ ДЛЯ ТАБЛИЦЫ nomenclature
-- ═══════════════════════════════════════════════════════════════════

-- Ускоряет поиск по названию
CREATE INDEX IF NOT EXISTS idx_nomenclature_name 
ON nomenclature(name);

-- Ускоряет фильтрацию по department_id
CREATE INDEX IF NOT EXISTS idx_nomenclature_department_id 
ON nomenclature(department_id);


-- ═══════════════════════════════════════════════════════════════════
-- 4. ИНДЕКСЫ ДЛЯ ТАБЛИЦЫ employees
-- ═══════════════════════════════════════════════════════════════════

-- Ускоряет поиск по имени
CREATE INDEX IF NOT EXISTS idx_employees_full_name 
ON employees(full_name);

-- Ускоряет фильтрацию по section_id
CREATE INDEX IF NOT EXISTS idx_employees_section_id 
ON employees(section_id);


-- ═══════════════════════════════════════════════════════════════════
-- 5. ИНДЕКСЫ ДЛЯ ТАБЛИЦЫ sections
-- ═══════════════════════════════════════════════════════════════════

-- Ускоряет поиск по названию
CREATE INDEX IF NOT EXISTS idx_sections_name 
ON sections(name);


-- ═══════════════════════════════════════════════════════════════════
-- 6. ИНДЕКСЫ ДЛЯ ТАБЛИЦЫ departments
-- ═══════════════════════════════════════════════════════════════════

-- Ускоряет поиск по названию
CREATE INDEX IF NOT EXISTS idx_departments_name 
ON departments(name);


-- ═══════════════════════════════════════════════════════════════════
-- АНАЛИЗ ТАБЛИЦ (обновление статистики для оптимизатора запросов)
-- ═══════════════════════════════════════════════════════════════════
ANALYZE fixed_assets;
ANALYZE work_orders;
ANALYZE nomenclature;
ANALYZE employees;
ANALYZE sections;
ANALYZE departments;


-- ═══════════════════════════════════════════════════════════════════
-- ПРОВЕРКА СОЗДАННЫХ ИНДЕКСОВ
-- ═══════════════════════════════════════════════════════════════════
SELECT 
    tablename,
    indexname
FROM pg_indexes 
WHERE schemaname = 'public' 
AND indexname LIKE 'idx_%'
ORDER BY tablename, indexname;
