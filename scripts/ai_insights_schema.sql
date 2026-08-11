-- ═══════════════════════════════════════════════════════════════════════════════
-- ТАБЛИЦА AI INSIGHTS
-- Хранение результатов ML-анализа: аномалии, прогнозы, эффективность
-- ═══════════════════════════════════════════════════════════════════════════════

DROP TABLE IF EXISTS public.ai_insights CASCADE;

CREATE TABLE public.ai_insights (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    equipment_id        text,                                    -- ID оборудования из fixed_assets
    work_order_id       text,                                    -- ID наряда из work_orders
    insight_type        text NOT NULL CHECK (insight_type IN ('anomaly', 'prediction', 'efficiency')),
    probability         numeric DEFAULT 0 CHECK (probability >= 0 AND probability <= 1),
    severity            text DEFAULT 'medium' CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    message             text NOT NULL,                           -- Описание инсайта
    suggested_action    text,                                    -- Рекомендация для руководства
    details             jsonb DEFAULT '{}',                      -- Дополнительные данные (метрики, параметры)
    is_resolved         boolean DEFAULT false,                   -- Отработан ли инсайт
    resolved_at         timestamptz,
    resolved_by         text,
    created_at          timestamptz NOT NULL DEFAULT now()
);

-- Индексы
CREATE INDEX idx_ai_insights_equipment ON public.ai_insights(equipment_id);
CREATE INDEX idx_ai_insights_work_order ON public.ai_insights(work_order_id);
CREATE INDEX idx_ai_insights_type ON public.ai_insights(insight_type);
CREATE INDEX idx_ai_insights_severity ON public.ai_insights(severity);
CREATE INDEX idx_ai_insights_created ON public.ai_insights(created_at DESC);
CREATE INDEX idx_ai_insights_unresolved ON public.ai_insights(is_resolved) WHERE is_resolved = false;

-- RLS
ALTER TABLE public.ai_insights ENABLE ROW LEVEL SECURITY;

CREATE POLICY "ai_insights_select" ON public.ai_insights
    FOR SELECT TO anon, authenticated USING (true);

CREATE POLICY "ai_insights_insert" ON public.ai_insights
    FOR INSERT TO anon, authenticated WITH CHECK (true);

CREATE POLICY "ai_insights_update" ON public.ai_insights
    FOR UPDATE TO anon, authenticated USING (true) WITH CHECK (true);

CREATE POLICY "ai_insights_delete" ON public.ai_insights
    FOR DELETE TO anon, authenticated USING (true);

-- Комментарии
COMMENT ON TABLE public.ai_insights IS 'Результаты ML-анализа: аномалии, прогнозы отказов, эффективность';
COMMENT ON COLUMN public.ai_insights.insight_type IS 'Тип: anomaly (аномалия расхода), prediction (прогноз отказа), efficiency (эффективность)';
COMMENT ON COLUMN public.ai_insights.probability IS 'Вероятность события (0-1), для prediction - вероятность отказа';
COMMENT ON COLUMN public.ai_insights.severity IS 'Критичность: low, medium, high, critical';

-- ═══════════════════════════════════════════════════════════════════════════════
-- ДОБАВЛЕНИЕ ПОЛЯ failure_probability В fixed_assets
-- ═══════════════════════════════════════════════════════════════════════════════

-- Добавляем колонку если её нет
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'fixed_assets' 
        AND column_name = 'failure_probability'
    ) THEN
        ALTER TABLE public.fixed_assets ADD COLUMN failure_probability numeric DEFAULT 0;
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'fixed_assets' 
        AND column_name = 'health_score'
    ) THEN
        ALTER TABLE public.fixed_assets ADD COLUMN health_score numeric DEFAULT 100;
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'fixed_assets' 
        AND column_name = 'predicted_failure_km'
    ) THEN
        ALTER TABLE public.fixed_assets ADD COLUMN predicted_failure_km numeric;
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'fixed_assets' 
        AND column_name = 'last_ml_update'
    ) THEN
        ALTER TABLE public.fixed_assets ADD COLUMN last_ml_update timestamptz;
    END IF;
END $$;

COMMENT ON COLUMN public.fixed_assets.failure_probability IS 'Вероятность отказа (0-1), рассчитывается ML';
COMMENT ON COLUMN public.fixed_assets.health_score IS 'Оценка здоровья оборудования (0-100)';
COMMENT ON COLUMN public.fixed_assets.predicted_failure_km IS 'Прогнозируемый пробег до отказа (км)';

-- ═══════════════════════════════════════════════════════════════════════════════
-- VIEW: Агрегация AI Insights для дашборда
-- ═══════════════════════════════════════════════════════════════════════════════

DROP VIEW IF EXISTS public.ai_insights_summary;

CREATE VIEW public.ai_insights_summary AS
SELECT 
    insight_type,
    severity,
    COUNT(*) AS total_count,
    COUNT(*) FILTER (WHERE NOT is_resolved) AS unresolved_count,
    AVG(probability) AS avg_probability,
    MAX(created_at) AS last_created
FROM public.ai_insights
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY insight_type, severity;

GRANT SELECT ON public.ai_insights_summary TO anon, authenticated;

-- ═══════════════════════════════════════════════════════════════════════════════
-- VIEW: Здоровье парка (Fleet Health)
-- ═══════════════════════════════════════════════════════════════════════════════

DROP VIEW IF EXISTS public.fleet_health;

CREATE VIEW public.fleet_health AS
SELECT 
    COUNT(*) AS total_assets,
    COUNT(*) FILTER (WHERE failure_probability < 0.2) AS healthy_count,
    COUNT(*) FILTER (WHERE failure_probability >= 0.2 AND failure_probability < 0.5) AS warning_count,
    COUNT(*) FILTER (WHERE failure_probability >= 0.5 AND failure_probability < 0.8) AS risk_count,
    COUNT(*) FILTER (WHERE failure_probability >= 0.8) AS critical_count,
    ROUND(AVG(COALESCE(health_score, 100))::numeric, 1) AS avg_health_score,
    ROUND((1 - AVG(COALESCE(failure_probability, 0)))::numeric * 100, 1) AS reliability_percent
FROM public.fixed_assets
WHERE asset_type IN ('locomotive', 'wagon');

GRANT SELECT ON public.fleet_health TO anon, authenticated;

-- ═══════════════════════════════════════════════════════════════════════════════
-- ФУНКЦИЯ: Webhook trigger для ML-обработки
-- ═══════════════════════════════════════════════════════════════════════════════

-- Функция для вызова при завершении наряда
CREATE OR REPLACE FUNCTION public.notify_ml_on_completion()
RETURNS TRIGGER AS $$
BEGIN
    -- Отправляем уведомление только при изменении статуса на 'completed'
    IF NEW.status = 'completed' AND (OLD.status IS NULL OR OLD.status != 'completed') THEN
        -- Используем pg_notify для внутреннего уведомления
        PERFORM pg_notify(
            'work_order_completed',
            json_build_object(
                'work_order_id', NEW.id,
                'unit', NEW.unit,
                'section', NEW.section,
                'repair_kind', NEW.repair_kind,
                'completed_at', NOW()
            )::text
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер на work_orders
DROP TRIGGER IF EXISTS trigger_ml_on_completion ON public.work_orders;

CREATE TRIGGER trigger_ml_on_completion
    AFTER UPDATE ON public.work_orders
    FOR EACH ROW
    EXECUTE FUNCTION public.notify_ml_on_completion();

COMMENT ON FUNCTION public.notify_ml_on_completion IS 'Уведомляет ML-систему о завершении наряда';
