CREATE TABLE IF NOT EXISTS daily_readiness_snapshots (
    snapshot_date date NOT NULL,
    scope_key varchar(40) NOT NULL,
    section_id uuid,
    asset_count integer NOT NULL CHECK (asset_count >= 0),
    ready_count integer NOT NULL CHECK (ready_count >= 0 AND ready_count <= asset_count),
    availability_percent numeric(5,2) NOT NULL CHECK (availability_percent BETWEEN 0 AND 100),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_date, scope_key)
);
CREATE INDEX IF NOT EXISTS ix_readiness_section_date
    ON daily_readiness_snapshots(section_id, snapshot_date);

CREATE OR REPLACE VIEW work_order_tmc_details AS
SELECT
    wo.id AS work_order_id,
    wo.number AS work_order_number,
    wo.fixed_asset_id AS asset_id,
    fa.name AS unit,
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
        fa.name AS unit,
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
        COUNT(d.tmc_item_id) AS tmc_count,
        COALESCE(SUM(d.tmc_qty), 0) AS total_qty,
        COALESCE(SUM(d.item_cost), 0) AS total_cost,
        COALESCE(SUM(d.norm_cost), 0) AS total_norm_cost,
        AVG(d.deviation_percent) AS avg_deviation_percent,
        COUNT(*) FILTER (WHERE d.deviation_percent > 20) AS overrun_count,
        string_agg(DISTINCT d.item_kind, ', ' ORDER BY d.item_kind)
            FILTER (WHERE d.item_kind IS NOT NULL) AS repair_kind,
        wo.mileage_at_creation AS current_mileage
    FROM work_orders wo
    JOIN fixed_assets fa ON fa.id = wo.fixed_asset_id
    JOIN sections s ON s.id = wo.section_id
    LEFT JOIN employees e ON e.id = wo.executor_id
    LEFT JOIN work_order_tmc_details d ON d.work_order_id = wo.id
    GROUP BY
        wo.id, wo.number, wo.fixed_asset_id, fa.name, fa.inv_number, fa.asset_type,
        wo.section_id, s.name, wo.department_id, wo.status, wo.order_kind,
        wo.priority, wo.description, wo.created_at, wo.closed_at, e.full_name,
        wo.mileage_at_creation
),
with_previous AS (
    SELECT
        costs.*,
        LAG(current_mileage) OVER (
            PARTITION BY asset_id, repair_kind ORDER BY created_at, work_order_id
        ) AS prev_mileage,
        LAG(created_at) OVER (
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
    COALESCE(current_mileage - prev_mileage, 0) AS mileage_between_orders,
    EXTRACT(DAY FROM (created_at - prev_order_date)) AS days_between_orders
FROM with_previous;

CREATE OR REPLACE VIEW section_efficiency AS
SELECT
    section_id,
    section,
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'completed') AS completed_orders,
    SUM(tmc_count) AS total_tmc_items,
    round(SUM(total_cost)::numeric, 0) AS total_actual_cost,
    round(SUM(total_norm_cost)::numeric, 0) AS total_norm_cost,
    round(SUM(cost_savings)::numeric, 0) AS total_savings,
    round(AVG(savings_percent)::numeric, 2) AS avg_savings_percent,
    round(AVG(avg_deviation_percent)::numeric, 2) AS avg_deviation_percent,
    SUM(overrun_count) AS total_overruns,
    round(AVG(mileage_between_orders)::numeric, 0) AS avg_mileage_between,
    round(AVG(days_between_orders)::numeric, 1) AS avg_days_between
FROM executive_summary
GROUP BY section_id, section;

CREATE OR REPLACE VIEW work_type_efficiency AS
SELECT
    es.section_id,
    es.section,
    d.item_kind AS repair_kind,
    COUNT(DISTINCT d.work_order_id) AS total_orders,
    round(SUM(d.item_cost)::numeric, 0) AS total_actual_cost,
    round(SUM(d.norm_cost)::numeric, 0) AS total_norm_cost,
    round(SUM(d.norm_cost - d.item_cost)::numeric, 0) AS total_savings,
    CASE WHEN SUM(d.norm_cost) > 0
        THEN round(((SUM(d.norm_cost) - SUM(d.item_cost)) / SUM(d.norm_cost) * 100)::numeric, 2)
        ELSE 0
    END AS avg_savings_percent,
    round(AVG(d.deviation_percent)::numeric, 2) AS avg_deviation_percent,
    round(AVG(es.mileage_between_orders)::numeric, 0) AS avg_mileage_between,
    COUNT(*) FILTER (WHERE d.deviation_percent > 20) AS total_overruns
FROM work_order_tmc_details d
JOIN executive_summary es ON es.work_order_id = d.work_order_id
GROUP BY es.section_id, es.section, d.item_kind;

CREATE OR REPLACE VIEW monthly_efficiency AS
SELECT
    date_trunc('month', created_at)::date AS month,
    section_id,
    section,
    COUNT(*) AS orders_count,
    round(SUM(total_cost)::numeric, 0) AS actual_cost,
    round(SUM(total_norm_cost)::numeric, 0) AS norm_cost,
    round(SUM(cost_savings)::numeric, 0) AS savings,
    round(AVG(savings_percent)::numeric, 2) AS avg_savings_percent
FROM executive_summary
GROUP BY date_trunc('month', created_at), section_id, section;

CREATE OR REPLACE VIEW ai_insights_summary AS
SELECT
    fa.section_id,
    ai.insight_type,
    ai.severity,
    COUNT(*) AS total_count,
    COUNT(*) FILTER (WHERE NOT ai.is_resolved) AS unresolved_count,
    AVG(ai.probability) AS avg_probability,
    MAX(ai.created_at) AS last_created
FROM ai_insights ai
LEFT JOIN fixed_assets fa ON fa.id = ai.asset_id
WHERE ai.created_at > now() - interval '30 days'
GROUP BY fa.section_id, ai.insight_type, ai.severity;

CREATE OR REPLACE VIEW fleet_health AS
SELECT
    section_id,
    COUNT(*) AS total_assets,
    COUNT(*) FILTER (WHERE failure_probability < 0.2) AS healthy_count,
    COUNT(*) FILTER (WHERE failure_probability >= 0.2 AND failure_probability < 0.5) AS warning_count,
    COUNT(*) FILTER (WHERE failure_probability >= 0.5 AND failure_probability < 0.8) AS risk_count,
    COUNT(*) FILTER (WHERE failure_probability >= 0.8) AS critical_count,
    round(AVG(COALESCE(health_score, 100))::numeric, 1) AS avg_health_score,
    round((1 - AVG(COALESCE(failure_probability, 0)))::numeric * 100, 1) AS reliability_percent
FROM fixed_assets
WHERE asset_type IN ('locomotive', 'diesel', 'wagon')
GROUP BY section_id;

CREATE OR REPLACE VIEW maintenance_schedule AS
SELECT
    mp.id AS plan_id,
    mp.asset_id,
    fa.name AS asset_name,
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
