-- Удаление тестовых данных
-- Выполните этот скрипт в Supabase SQL Editor

-- 1. Удаляем тестовые наряды (WO-ML-XXXX)
DELETE FROM public.work_orders WHERE id LIKE 'WO-ML-%';

-- 2. Удаляем тестовые AI insights
DELETE FROM public.ai_insights WHERE id IS NOT NULL;

-- 3. Удаляем тестовое оборудование
DELETE FROM public.fixed_assets WHERE name IN (
    'TEP70-0325',
    '2TE116-1542', 
    'VL80S-2105',
    'CHS7-089',
    '61-788-045'
);

-- 4. Удаляем тестовые вагоны Wagon-XXX
DELETE FROM public.fixed_assets WHERE name LIKE 'Wagon-%';

-- 5. Сбрасываем ML-поля у оставшегося оборудования
UPDATE public.fixed_assets 
SET failure_probability = 0,
    health_score = 100,
    predicted_failure_km = NULL,
    last_ml_update = NULL
WHERE failure_probability > 0 OR health_score < 100;

-- Проверка результатов
SELECT 'Work orders deleted' AS action, COUNT(*) AS before FROM public.work_orders WHERE id LIKE 'WO-ML-%';
SELECT 'Test equipment remaining' AS action, COUNT(*) AS count FROM public.fixed_assets WHERE name LIKE 'Wagon-%' OR name IN ('TEP70-0325', '2TE116-1542', 'VL80S-2105', 'CHS7-089', '61-788-045');
SELECT 'AI insights remaining' AS action, COUNT(*) AS count FROM public.ai_insights;
