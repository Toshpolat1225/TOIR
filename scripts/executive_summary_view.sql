-- ═══════════════════════════════════════════════════════════════════════════════
-- SQL View: executive_summary
-- Объединяет данные из work_orders, fixed_assets (equipment) и nomenclature_norms
-- Рассчитывает отклонения, стоимость и пробег между нарядами
-- ═══════════════════════════════════════════════════════════════════════════════

-- Удаляем существующую view если есть
DROP VIEW IF EXISTS public.executive_summary;

-- ═══════════════════════════════════════════════════════════════════════════════
-- Вспомогательная view для расчёта ТМЦ по нарядам
-- ═══════════════════════════════════════════════════════════════════════════════
DROP VIEW IF EXISTS public.work_order_tmc_details;

CREATE VIEW public.work_order_tmc_details AS
WITH tmc_items AS (
    -- Извлекаем ТМЦ из JSON массива repair_items
    SELECT 
        wo.id AS work_order_id,
        wo.unit,
        wo.section,
        wo.repair_kind,
        wo.status,
        wo.created_at,
        wo.closed,
        wo.tech,
        wo.unit_type,
        -- Извлекаем данные из JSONB
        item->>'kind' AS item_kind,
        row_data->>'name' AS tmc_name,
        row_data->>'invNo' AS tmc_inv_no,
        row_data->>'unit' AS tmc_unit,
        COALESCE((row_data->>'qty')::numeric, 0) AS tmc_qty
    FROM public.work_orders wo,
        jsonb_array_elements(wo.repair_items) AS item,
        jsonb_array_elements(item->'rows') AS row_data
    WHERE wo.repair_items IS NOT NULL 
      AND jsonb_array_length(wo.repair_items) > 0
)
SELECT 
    ti.work_order_id,
    ti.unit,
    ti.section,
    ti.repair_kind,
    ti.status,
    ti.created_at,
    ti.closed,
    ti.tech,
    ti.unit_type,
    ti.item_kind,
    ti.tmc_name,
    ti.tmc_inv_no,
    ti.tmc_unit,
    ti.tmc_qty,
    -- Получаем section_id
    s.id AS section_id,
    -- Получаем нормативы
    nn.standard_quantity,
    nn.avg_price,
    -- Расчёт отклонения от нормы в процентах
    CASE 
        WHEN nn.standard_quantity > 0 THEN 
            ROUND(((ti.tmc_qty - nn.standard_quantity) / nn.standard_quantity * 100)::numeric, 2)
        ELSE 0 
    END AS deviation_percent,
    -- Расчёт стоимости (количество * цена)
    ROUND((ti.tmc_qty * COALESCE(nn.avg_price, 0))::numeric, 2) AS item_cost,
    -- Норматив стоимости
    ROUND((nn.standard_quantity * COALESCE(nn.avg_price, 0))::numeric, 2) AS norm_cost
FROM tmc_items ti
LEFT JOIN public.sections s ON s.name = ti.section
LEFT JOIN public.nomenclature n ON n.name = ti.tmc_name OR n.code = ti.tmc_inv_no
LEFT JOIN public.nomenclature_norms nn ON nn.nomenclature_id = n.id::text 
    AND nn.department_id = s.id::text 
    AND (nn.work_type = ti.item_kind OR nn.work_type = ti.repair_kind);

-- ═══════════════════════════════════════════════════════════════════════════════
-- Основная view: executive_summary
-- ═══════════════════════════════════════════════════════════════════════════════
CREATE VIEW public.executive_summary AS
WITH work_order_costs AS (
    -- Агрегируем стоимость и отклонения по нарядам
    SELECT 
        work_order_id,
        unit,
        section,
        section_id,
        repair_kind,
        status,
        created_at,
        closed,
        tech,
        unit_type,
        COUNT(*) AS tmc_count,
        SUM(tmc_qty) AS total_qty,
        SUM(item_cost) AS total_cost,
        SUM(norm_cost) AS total_norm_cost,
        AVG(deviation_percent) AS avg_deviation_percent,
        SUM(CASE WHEN deviation_percent > 20 THEN 1 ELSE 0 END) AS overrun_count
    FROM public.work_order_tmc_details
    GROUP BY work_order_id, unit, section, section_id, repair_kind, status, 
             created_at, closed, tech, unit_type
),
with_mileage AS (
    -- Добавляем данные о пробеге из fixed_assets
    SELECT 
        woc.*,
        fa.id AS asset_id,
        fa.mileage AS current_mileage,
        fa.last_maint,
        -- Пробег между текущим и прошлым нарядом по этому же типу работ
        LAG(fa.mileage) OVER (
            PARTITION BY woc.unit, woc.repair_kind 
            ORDER BY woc.created_at
        ) AS prev_mileage,
        LAG(woc.created_at) OVER (
            PARTITION BY woc.unit, woc.repair_kind 
            ORDER BY woc.created_at
        ) AS prev_order_date
    FROM work_order_costs woc
    LEFT JOIN public.fixed_assets fa ON fa.name = woc.unit
)
SELECT 
    work_order_id,
    unit,
    section,
    section_id,
    repair_kind,
    status,
    created_at,
    closed,
    tech,
    unit_type,
    tmc_count,
    total_qty,
    total_cost,
    total_norm_cost,
    -- Экономия или перерасход
    ROUND((total_norm_cost - total_cost)::numeric, 2) AS cost_savings,
    -- Процент экономии/перерасхода
    CASE 
        WHEN total_norm_cost > 0 THEN 
            ROUND(((total_norm_cost - total_cost) / total_norm_cost * 100)::numeric, 2)
        ELSE 0 
    END AS savings_percent,
    avg_deviation_percent,
    overrun_count,
    asset_id,
    current_mileage,
    prev_mileage,
    -- Пробег между нарядами
    COALESCE(current_mileage::numeric - prev_mileage::numeric, 0) AS mileage_between_orders,
    prev_order_date,
    -- Дней между нарядами
    EXTRACT(DAY FROM (created_at - prev_order_date)) AS days_between_orders
FROM with_mileage;

-- ═══════════════════════════════════════════════════════════════════════════════
-- Агрегированная view по участкам для Dashboard
-- ═══════════════════════════════════════════════════════════════════════════════
DROP VIEW IF EXISTS public.section_efficiency;

CREATE VIEW public.section_efficiency AS
SELECT 
    section,
    section_id,
    COUNT(*) AS total_orders,
    COUNT(CASE WHEN status = 'completed' THEN 1 END) AS completed_orders,
    SUM(tmc_count) AS total_tmc_items,
    ROUND(SUM(total_cost)::numeric, 0) AS total_actual_cost,
    ROUND(SUM(total_norm_cost)::numeric, 0) AS total_norm_cost,
    ROUND(SUM(cost_savings)::numeric, 0) AS total_savings,
    ROUND(AVG(savings_percent)::numeric, 2) AS avg_savings_percent,
    ROUND(AVG(avg_deviation_percent)::numeric, 2) AS avg_deviation_percent,
    SUM(overrun_count) AS total_overruns,
    ROUND(AVG(mileage_between_orders)::numeric, 0) AS avg_mileage_between,
    ROUND(AVG(days_between_orders)::numeric, 1) AS avg_days_between
FROM public.executive_summary
WHERE section IS NOT NULL
GROUP BY section, section_id;

-- ═══════════════════════════════════════════════════════════════════════════════
-- Агрегированная view по видам работ
-- ═══════════════════════════════════════════════════════════════════════════════
DROP VIEW IF EXISTS public.work_type_efficiency;

CREATE VIEW public.work_type_efficiency AS
SELECT 
    repair_kind,
    COUNT(*) AS total_orders,
    ROUND(SUM(total_cost)::numeric, 0) AS total_actual_cost,
    ROUND(SUM(total_norm_cost)::numeric, 0) AS total_norm_cost,
    ROUND(SUM(cost_savings)::numeric, 0) AS total_savings,
    ROUND(AVG(savings_percent)::numeric, 2) AS avg_savings_percent,
    ROUND(AVG(avg_deviation_percent)::numeric, 2) AS avg_deviation_percent,
    ROUND(AVG(mileage_between_orders)::numeric, 0) AS avg_mileage_between
FROM public.executive_summary
WHERE repair_kind IS NOT NULL AND repair_kind != ''
GROUP BY repair_kind;

-- ═══════════════════════════════════════════════════════════════════════════════
-- Месячная статистика
-- ═══════════════════════════════════════════════════════════════════════════════
DROP VIEW IF EXISTS public.monthly_efficiency;

CREATE VIEW public.monthly_efficiency AS
SELECT 
    DATE_TRUNC('month', created_at)::date AS month,
    section,
    COUNT(*) AS orders_count,
    ROUND(SUM(total_cost)::numeric, 0) AS actual_cost,
    ROUND(SUM(total_norm_cost)::numeric, 0) AS norm_cost,
    ROUND(SUM(cost_savings)::numeric, 0) AS savings,
    ROUND(AVG(savings_percent)::numeric, 2) AS avg_savings_percent
FROM public.executive_summary
WHERE created_at IS NOT NULL
GROUP BY DATE_TRUNC('month', created_at), section
ORDER BY month DESC, section;

-- ═══════════════════════════════════════════════════════════════════════════════
-- Права доступа
-- ═══════════════════════════════════════════════════════════════════════════════
GRANT SELECT ON public.executive_summary TO anon, authenticated;
GRANT SELECT ON public.work_order_tmc_details TO anon, authenticated;
GRANT SELECT ON public.section_efficiency TO anon, authenticated;
GRANT SELECT ON public.work_type_efficiency TO anon, authenticated;
GRANT SELECT ON public.monthly_efficiency TO anon, authenticated;

-- ═══════════════════════════════════════════════════════════════════════════════
-- Комментарии
-- ═══════════════════════════════════════════════════════════════════════════════
COMMENT ON VIEW public.executive_summary IS 'Сводная аналитика по нарядам: стоимость, отклонения, пробег';
COMMENT ON VIEW public.section_efficiency IS 'Экономическая эффективность по участкам';
COMMENT ON VIEW public.work_type_efficiency IS 'Эффективность по видам работ';
COMMENT ON VIEW public.monthly_efficiency IS 'Месячная статистика эффективности';
