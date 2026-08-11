# Настройка Webhook для ML-обработки

## Обзор

При завершении наряда (статус = 'completed') система автоматически запускает ML-анализ:
- Детекция аномалий расхода ТМЦ
- Прогноз отказов (RUL)
- Обновление health score оборудования

## Способ 1: Database Webhook (Supabase Dashboard)

### Шаг 1: Создайте Edge Function или внешний endpoint

Разверните ML-скрипт как веб-сервис:

```bash
# Локальный запуск
cd services
python ml_engine.py --serve --port 5000

# Или разверните на сервере (например, Railway, Render, VPS)
```

### Шаг 2: Настройте Webhook в Supabase

1. Откройте **Supabase Dashboard** → **Database** → **Webhooks**
2. Нажмите **Create a new webhook**
3. Заполните форму:

| Поле | Значение |
|------|----------|
| Name | `ml_work_order_completed` |
| Table | `work_orders` |
| Events | ☑ UPDATE |
| HTTP Method | POST |
| URL | `https://your-server.com/webhook/work-order-completed` |
| HTTP Headers | `Content-Type: application/json` |

4. Добавьте фильтр (Filter):
```sql
new.status = 'completed' AND (old.status IS NULL OR old.status != 'completed')
```

5. Сохраните webhook

## Способ 2: PostgreSQL Trigger + pg_net (рекомендуется)

### Шаг 1: Включите расширение pg_net

```sql
-- Выполните в SQL Editor
CREATE EXTENSION IF NOT EXISTS pg_net;
```

### Шаг 2: Создайте функцию для HTTP-запроса

```sql
CREATE OR REPLACE FUNCTION public.call_ml_webhook()
RETURNS TRIGGER AS $$
DECLARE
    response_id bigint;
BEGIN
    -- Отправляем POST-запрос только при завершении наряда
    IF NEW.status = 'completed' AND (OLD.status IS NULL OR OLD.status != 'completed') THEN
        SELECT net.http_post(
            url := 'https://your-server.com/webhook/work-order-completed',
            headers := '{"Content-Type": "application/json"}'::jsonb,
            body := json_build_object(
                'record', row_to_json(NEW),
                'old_record', row_to_json(OLD),
                'type', 'UPDATE',
                'table', 'work_orders'
            )::jsonb
        ) INTO response_id;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Создаём триггер
DROP TRIGGER IF EXISTS trigger_ml_webhook ON public.work_orders;

CREATE TRIGGER trigger_ml_webhook
    AFTER UPDATE ON public.work_orders
    FOR EACH ROW
    EXECUTE FUNCTION public.call_ml_webhook();
```

## Способ 3: Supabase Edge Functions

### Шаг 1: Создайте Edge Function

```bash
supabase functions new ml-processor
```

### Шаг 2: Код функции (supabase/functions/ml-processor/index.ts)

```typescript
import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

serve(async (req) => {
  const { record, old_record, type, table } = await req.json()
  
  // Проверяем, что это завершение наряда
  if (table !== 'work_orders' || type !== 'UPDATE') {
    return new Response(JSON.stringify({ status: 'skipped' }), { status: 200 })
  }
  
  if (record.status !== 'completed' || old_record?.status === 'completed') {
    return new Response(JSON.stringify({ status: 'skipped' }), { status: 200 })
  }
  
  const supabase = createClient(
    Deno.env.get('SUPABASE_URL') ?? '',
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''
  )
  
  // Здесь можно добавить ML-логику или вызвать внешний сервис
  // ...
  
  return new Response(JSON.stringify({ status: 'processed' }), { status: 200 })
})
```

### Шаг 3: Настройте Database Webhook на Edge Function

URL: `https://<project-ref>.supabase.co/functions/v1/ml-processor`

## Способ 4: Ручной запуск (для тестирования)

```bash
# Анализ всего оборудования
python services/ml_engine.py --analyze

# Обработка конкретного наряда
python services/ml_engine.py --work-order "WO-2024-001"
```

## Проверка работы

1. Завершите любой наряд в системе
2. Проверьте таблицу `ai_insights`:

```sql
SELECT * FROM ai_insights ORDER BY created_at DESC LIMIT 5;
```

3. Проверьте обновление `fixed_assets`:

```sql
SELECT name, failure_probability, health_score, predicted_failure_km 
FROM fixed_assets 
WHERE failure_probability > 0
ORDER BY failure_probability DESC;
```

## Мониторинг

### Логи webhook-ов

```sql
-- Если используете pg_net
SELECT * FROM net._http_response ORDER BY created DESC LIMIT 10;
```

### Статистика AI Insights

```sql
SELECT 
    insight_type,
    severity,
    COUNT(*) as count,
    AVG(probability) as avg_prob
FROM ai_insights
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY insight_type, severity;
```

## Безопасность

1. **Аутентификация webhook**: Добавьте секретный токен в заголовки
2. **Rate limiting**: Ограничьте частоту вызовов
3. **Валидация payload**: Проверяйте структуру входящих данных

```python
# В ml_engine.py добавьте проверку токена
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', 'your-secret-token')

@app.route("/webhook/work-order-completed", methods=["POST"])
def handle_webhook():
    # Проверка токена
    token = request.headers.get('X-Webhook-Secret')
    if token != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    # ...
```
