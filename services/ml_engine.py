"""
ML Engine - Фоновый процессор для прогнозирования поломок и анализа аномалий

Функции:
1. Анализ аномалий расхода ТМЦ (IsolationForest + Z-score)
2. Прогноз отказов (RUL - Remaining Useful Life)
3. Расчёт здоровья оборудования

Запуск:
    # Однократный анализ
    python services/ml_engine.py --analyze
    
    # Обработка конкретного наряда
    python services/ml_engine.py --work-order "WO-2024-001"
    
    # Фоновый режим (слушает PostgreSQL NOTIFY)
    python services/ml_engine.py --listen
    
    # Webhook endpoint (Flask)
    python services/ml_engine.py --serve --port 5000

Требования:
    pip install pandas numpy scikit-learn supabase flask
"""

import os
import sys
import json
import uuid
import argparse
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler

from supabase import create_client, Client

# ═══════════════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════════

SUPABASE_URL = "https://qowgaahijzamnprtfyko.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFvd2dhYWhpanphbW5wcnRmeWtvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE0Njc2MTQsImV4cCI6MjA4NzA0MzYxNH0.zo-bAha0qyNw37yRkitt6f-nF1Gt2hYnanZ5zah-eaA"

# Пороги для аномалий
ANOMALY_ZSCORE_THRESHOLD = 2.0      # Z-score > 2 = аномалия
ANOMALY_DEVIATION_THRESHOLD = 0.3   # Отклонение > 30% = аномалия
ISOLATION_FOREST_CONTAMINATION = 0.1

# Пороги для прогнозов
HIGH_RISK_PROBABILITY = 0.7
MEDIUM_RISK_PROBABILITY = 0.4
CRITICAL_MILEAGE_THRESHOLD = 500    # км до отказа

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# SUPABASE CLIENT
# ═══════════════════════════════════════════════════════════════════════════════

def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ═══════════════════════════════════════════════════════════════════════════════
# ЗАГРУЗКА ДАННЫХ
# ═══════════════════════════════════════════════════════════════════════════════

def load_work_order_history(supabase: Client, unit: str, limit: int = 100) -> pd.DataFrame:
    """Загружает историю нарядов для конкретного оборудования"""
    response = supabase.table("work_orders").select(
        "id, unit, section, repair_kind, status, created_at, closed, repair_items"
    ).eq("unit", unit).eq("status", "completed").order(
        "created_at", desc=True
    ).limit(limit).execute()
    
    if not response.data:
        return pd.DataFrame()
    
    return pd.DataFrame(response.data)


def load_equipment_data(supabase: Client, unit_name: str) -> Optional[Dict]:
    """Загружает данные оборудования"""
    response = supabase.table("fixed_assets").select("*").eq("name", unit_name).limit(1).execute()
    if response.data:
        return response.data[0]
    return None


def load_historical_tmc_stats(supabase: Client, repair_kind: str, section: str) -> Dict:
    """Загружает историческую статистику расхода ТМЦ для типа работ"""
    # Получаем все завершённые наряды этого типа
    response = supabase.table("work_orders").select(
        "repair_items"
    ).eq("repair_kind", repair_kind).eq("section", section).eq("status", "completed").limit(200).execute()
    
    if not response.data:
        return {"mean": 0, "std": 1, "count": 0}
    
    # Считаем общее количество ТМЦ в каждом наряде
    quantities = []
    for wo in response.data:
        items = wo.get("repair_items") or []
        total_qty = 0
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    for row in item.get("rows", []):
                        try:
                            total_qty += float(row.get("qty", 0) or 0)
                        except (ValueError, TypeError):
                            pass
        quantities.append(total_qty)
    
    if not quantities:
        return {"mean": 0, "std": 1, "count": 0}
    
    return {
        "mean": np.mean(quantities),
        "std": np.std(quantities) if len(quantities) > 1 else 1,
        "count": len(quantities)
    }


def extract_tmc_total(repair_items: Any) -> float:
    """Извлекает общее количество ТМЦ из repair_items"""
    if not repair_items:
        return 0
    
    total = 0
    if isinstance(repair_items, list):
        for item in repair_items:
            if isinstance(item, dict):
                for row in item.get("rows", []):
                    try:
                        total += float(row.get("qty", 0) or 0)
                    except (ValueError, TypeError):
                        pass
    return total


# ═══════════════════════════════════════════════════════════════════════════════
# АНАЛИЗ АНОМАЛИЙ
# ═══════════════════════════════════════════════════════════════════════════════

def detect_anomaly_zscore(current_value: float, mean: float, std: float) -> Tuple[bool, float]:
    """Детекция аномалии методом Z-score"""
    if std == 0:
        return False, 0.0
    
    zscore = abs(current_value - mean) / std
    is_anomaly = zscore > ANOMALY_ZSCORE_THRESHOLD
    
    return is_anomaly, zscore


def detect_anomaly_isolation_forest(data: np.ndarray) -> np.ndarray:
    """Детекция аномалий методом Isolation Forest"""
    if len(data) < 5:
        return np.zeros(len(data), dtype=bool)
    
    # Reshape для sklearn
    X = data.reshape(-1, 1)
    
    # Нормализация
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Isolation Forest
    iso_forest = IsolationForest(
        contamination=ISOLATION_FOREST_CONTAMINATION,
        random_state=42,
        n_estimators=100
    )
    
    predictions = iso_forest.fit_predict(X_scaled)
    
    # -1 = аномалия, 1 = норма
    return predictions == -1


def analyze_tmc_anomaly(
    supabase: Client,
    work_order_id: str,
    unit: str,
    repair_kind: str,
    section: str,
    current_tmc_qty: float
) -> Optional[Dict]:
    """Анализирует расход ТМЦ на аномалии"""
    
    # Получаем историческую статистику
    stats = load_historical_tmc_stats(supabase, repair_kind, section)
    
    if stats["count"] < 3:
        logger.info(f"Недостаточно исторических данных для {repair_kind}/{section}")
        return None
    
    # Z-score анализ
    is_anomaly, zscore = detect_anomaly_zscore(
        current_tmc_qty, 
        stats["mean"], 
        stats["std"]
    )
    
    # Расчёт отклонения в процентах
    if stats["mean"] > 0:
        deviation_pct = (current_tmc_qty - stats["mean"]) / stats["mean"]
    else:
        deviation_pct = 0
    
    # Проверка порога отклонения
    is_significant = abs(deviation_pct) > ANOMALY_DEVIATION_THRESHOLD
    
    if not (is_anomaly or is_significant):
        return None
    
    # Определяем severity
    if abs(deviation_pct) > 0.5 or zscore > 3:
        severity = "critical"
    elif abs(deviation_pct) > 0.3 or zscore > 2.5:
        severity = "high"
    else:
        severity = "medium"
    
    # Формируем сообщение с названием оборудования
    direction = "превышение" if deviation_pct > 0 else "экономия"
    message = (
        f"{unit}: Аномальный расход ТМЦ - {direction} на {abs(deviation_pct)*100:.1f}% "
        f"(факт: {current_tmc_qty:.1f}, норма: {stats['mean']:.1f})"
    )
    
    # Рекомендация
    if deviation_pct > 0.3:
        action = "Проверить обоснованность расхода. Возможно нецелевое использование материалов."
    elif deviation_pct < -0.3:
        action = "Проверить качество выполненных работ. Возможна экономия на материалах."
    else:
        action = "Провести выборочную проверку документации."
    
    return {
        "insight_type": "anomaly",
        "probability": min(abs(zscore) / 4, 1.0),  # Нормализуем zscore в вероятность
        "severity": severity,
        "message": message,
        "suggested_action": action,
        "details": {
            "zscore": round(zscore, 2),
            "deviation_percent": round(deviation_pct * 100, 1),
            "current_qty": current_tmc_qty,
            "historical_mean": round(stats["mean"], 2),
            "historical_std": round(stats["std"], 2),
            "sample_size": stats["count"]
        }
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОГНОЗ ОТКАЗОВ (RUL - Remaining Useful Life)
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_rul(supabase: Client, unit: str, equipment: Dict) -> Optional[Dict]:
    """
    Рассчитывает RUL (Remaining Useful Life) на основе:
    - Истории ремонтов
    - Текущего пробега
    - Интервалов между ремонтами
    """
    
    # Загружаем историю нарядов
    history = load_work_order_history(supabase, unit, limit=50)
    
    if len(history) < 3:
        logger.info(f"Недостаточно истории для прогноза RUL: {unit}")
        return None
    
    # Преобразуем даты
    history["created_at"] = pd.to_datetime(history["created_at"])
    history = history.sort_values("created_at")
    
    # Рассчитываем интервалы между ремонтами (в днях)
    history["days_since_prev"] = history["created_at"].diff().dt.days
    
    # Убираем первую строку (NaN)
    intervals = history["days_since_prev"].dropna().values
    
    if len(intervals) < 2:
        return None
    
    # Линейная регрессия для прогноза тренда
    X = np.arange(len(intervals)).reshape(-1, 1)
    y = intervals
    
    model = LinearRegression()
    model.fit(X, y)
    
    # Прогноз следующего интервала
    next_interval = model.predict([[len(intervals)]])[0]
    
    # Текущий пробег и последний ремонт
    current_mileage = equipment.get("mileage", 0) or 0
    last_maintenance = equipment.get("last_maint")  # Используем реальное имя колонки
    
    # Средний пробег между ремонтами (рассчитываем из истории или используем default)
    avg_mileage_between = 5000  # Default значение
    
    # Дней с последнего ремонта
    if last_maintenance:
        try:
            last_date = pd.to_datetime(last_maintenance)
            days_since_last = (datetime.now() - last_date.to_pydatetime().replace(tzinfo=None)).days
        except:
            days_since_last = 0
    else:
        days_since_last = 0
    
    # Расчёт вероятности отказа
    # Используем экспоненциальное распределение
    mean_interval = np.mean(intervals)
    if mean_interval > 0:
        # Вероятность отказа растёт с приближением к среднему интервалу
        failure_prob = 1 - np.exp(-days_since_last / mean_interval)
    else:
        failure_prob = 0.5
    
    # Прогноз пробега до отказа
    if next_interval > 0 and avg_mileage_between > 0:
        # Примерный пробег в день
        daily_mileage = avg_mileage_between / mean_interval if mean_interval > 0 else 100
        remaining_days = max(0, next_interval - days_since_last)
        predicted_km = remaining_days * daily_mileage
    else:
        predicted_km = None
    
    # Определяем severity
    if failure_prob >= HIGH_RISK_PROBABILITY:
        severity = "critical" if predicted_km and predicted_km < CRITICAL_MILEAGE_THRESHOLD else "high"
    elif failure_prob >= MEDIUM_RISK_PROBABILITY:
        severity = "medium"
    else:
        severity = "low"
    
    # Получаем название оборудования
    unit_name = equipment.get("name", unit)
    
    # Формируем сообщение с названием оборудования
    if predicted_km and predicted_km < CRITICAL_MILEAGE_THRESHOLD:
        message = (
            f"{unit_name}: Высокий риск отказа через ~{predicted_km:.0f} км. "
            f"Вероятность: {failure_prob*100:.0f}%"
        )
        action = "Рекомендуется внеплановый осмотр и диагностика."
    elif failure_prob >= HIGH_RISK_PROBABILITY:
        message = (
            f"{unit_name}: Повышенный риск отказа. Вероятность: {failure_prob*100:.0f}%. "
            f"Дней с последнего ТО: {days_since_last}"
        )
        action = "Запланировать техническое обслуживание в ближайшее время."
    elif failure_prob >= MEDIUM_RISK_PROBABILITY:
        message = (
            f"{unit_name}: Умеренный риск. Вероятность отказа: {failure_prob*100:.0f}%"
        )
        action = "Контролировать состояние при следующем осмотре."
    else:
        # Низкий риск - не создаём инсайт
        return None
    
    return {
        "insight_type": "prediction",
        "probability": round(failure_prob, 3),
        "severity": severity,
        "message": message,
        "suggested_action": action,
        "details": {
            "days_since_last_maintenance": days_since_last,
            "mean_interval_days": round(mean_interval, 1),
            "predicted_next_interval": round(next_interval, 1),
            "predicted_km_to_failure": round(predicted_km, 0) if predicted_km else None,
            "current_mileage": current_mileage,
            "repair_count": len(history)
        }
    }


# ═══════════════════════════════════════════════════════════════════════════════
# РАСЧЁТ ЗДОРОВЬЯ ОБОРУДОВАНИЯ
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_health_score(
    failure_probability: float,
    anomaly_count: int,
    days_since_maintenance: int,
    mileage_since_maintenance: float
) -> float:
    """
    Рассчитывает оценку здоровья оборудования (0-100)
    """
    # Базовый скор от вероятности отказа
    base_score = (1 - failure_probability) * 100
    
    # Штраф за аномалии
    anomaly_penalty = min(anomaly_count * 5, 20)
    
    # Штраф за время без ТО (макс 15 баллов)
    time_penalty = min(days_since_maintenance / 30 * 5, 15)
    
    # Итоговый скор
    health = max(0, base_score - anomaly_penalty - time_penalty)
    
    return round(health, 1)


# ═══════════════════════════════════════════════════════════════════════════════
# СОХРАНЕНИЕ РЕЗУЛЬТАТОВ
# ═══════════════════════════════════════════════════════════════════════════════

def save_insight(supabase: Client, insight: Dict, equipment_id: str = None, work_order_id: str = None):
    """Сохраняет инсайт в базу данных"""
    record = {
        "id": str(uuid.uuid4()),
        "equipment_id": equipment_id,
        "work_order_id": work_order_id,
        "insight_type": insight["insight_type"],
        "probability": insight["probability"],
        "severity": insight["severity"],
        "message": insight["message"],
        "suggested_action": insight.get("suggested_action"),
        "details": insight.get("details", {}),
        "created_at": datetime.now().isoformat()
    }
    
    try:
        supabase.table("ai_insights").insert(record).execute()
        logger.info(f"Saved insight: {insight['insight_type']} - {insight['severity']}")
    except Exception as e:
        logger.error(f"Failed to save insight: {e}")


def update_equipment_ml_fields(
    supabase: Client,
    equipment_id: str,
    failure_probability: float,
    health_score: float,
    predicted_km: float = None
):
    """Обновляет ML-поля в таблице оборудования"""
    update_data = {
        "failure_probability": failure_probability,
        "health_score": health_score,
        "last_ml_update": datetime.now().isoformat()
    }
    
    if predicted_km is not None:
        update_data["predicted_failure_km"] = predicted_km
    
    try:
        supabase.table("fixed_assets").update(update_data).eq("id", equipment_id).execute()
        logger.info(f"Updated equipment {equipment_id}: prob={failure_probability:.2f}, health={health_score}")
    except Exception as e:
        logger.error(f"Failed to update equipment: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# ОСНОВНЫЕ ФУНКЦИИ ОБРАБОТКИ
# ═══════════════════════════════════════════════════════════════════════════════

def process_completed_work_order(supabase: Client, work_order_id: str):
    """Обрабатывает завершённый наряд"""
    logger.info(f"Processing work order: {work_order_id}")
    
    # Загружаем данные наряда
    response = supabase.table("work_orders").select("*").eq("id", work_order_id).limit(1).execute()
    
    if not response.data:
        logger.warning(f"Work order not found: {work_order_id}")
        return
    
    wo = response.data[0]
    unit = wo.get("unit", "")
    section = wo.get("section", "")
    repair_kind = wo.get("repair_kind", "")
    repair_items = wo.get("repair_items")
    
    # Загружаем данные оборудования
    equipment = load_equipment_data(supabase, unit)
    equipment_id = equipment.get("id") if equipment else None
    
    # 1. Анализ аномалий расхода ТМЦ
    current_tmc_qty = extract_tmc_total(repair_items)
    
    if current_tmc_qty > 0:
        anomaly = analyze_tmc_anomaly(
            supabase, work_order_id, unit, repair_kind, section, current_tmc_qty
        )
        if anomaly:
            save_insight(supabase, anomaly, equipment_id, work_order_id)
    
    # 2. Прогноз отказов (RUL)
    if equipment:
        rul_insight = calculate_rul(supabase, unit, equipment)
        if rul_insight:
            save_insight(supabase, rul_insight, equipment_id, work_order_id)
            
            # Обновляем поля оборудования
            failure_prob = rul_insight["probability"]
            predicted_km = rul_insight["details"].get("predicted_km_to_failure")
            
            # Считаем количество аномалий за последние 30 дней
            anomaly_response = supabase.table("ai_insights").select(
                "id", count="exact"
            ).eq("equipment_id", equipment_id).eq(
                "insight_type", "anomaly"
            ).gte("created_at", (datetime.now() - timedelta(days=30)).isoformat()).execute()
            
            anomaly_count = anomaly_response.count or 0
            
            # Дней с последнего ТО
            days_since = rul_insight["details"].get("days_since_last_maintenance", 0)
            
            # Расчёт health score
            health = calculate_health_score(failure_prob, anomaly_count, days_since, 0)
            
            update_equipment_ml_fields(supabase, equipment_id, failure_prob, health, predicted_km)
    
    logger.info(f"Completed processing: {work_order_id}")


def analyze_all_equipment(supabase: Client):
    """Анализирует всё оборудование"""
    logger.info("Starting full equipment analysis...")
    
    # Загружаем всё оборудование (используем реальные имена колонок)
    response = supabase.table("fixed_assets").select(
        "id, name, mileage, last_maint, asset_type"
    ).in_("asset_type", ["locomotive", "wagon"]).execute()
    
    if not response.data:
        logger.warning("No equipment found")
        return
    
    for equipment in response.data:
        unit = equipment.get("name", "")
        if not unit:
            continue
        
        logger.info(f"Analyzing: {unit}")
        
        # Прогноз RUL
        rul_insight = calculate_rul(supabase, unit, equipment)
        if rul_insight:
            save_insight(supabase, rul_insight, equipment["id"])
            
            # Обновляем поля
            failure_prob = rul_insight["probability"]
            predicted_km = rul_insight["details"].get("predicted_km_to_failure")
            days_since = rul_insight["details"].get("days_since_last_maintenance", 0)
            
            health = calculate_health_score(failure_prob, 0, days_since, 0)
            update_equipment_ml_fields(supabase, equipment["id"], failure_prob, health, predicted_km)
    
    logger.info("Full analysis completed")


# ═══════════════════════════════════════════════════════════════════════════════
# FLASK WEBHOOK ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════════

def create_webhook_app():
    """Создаёт Flask приложение для webhook"""
    try:
        from flask import Flask, request, jsonify
    except ImportError:
        logger.error("Flask not installed. Run: pip install flask")
        return None
    
    app = Flask(__name__)
    
    @app.route("/webhook/work-order-completed", methods=["POST"])
    def handle_work_order_completed():
        """Обработчик webhook от Supabase"""
        try:
            data = request.json
            
            # Supabase webhook payload
            record = data.get("record", {})
            old_record = data.get("old_record", {})
            
            # Проверяем, что статус изменился на completed
            if record.get("status") == "completed" and old_record.get("status") != "completed":
                work_order_id = record.get("id")
                
                if work_order_id:
                    supabase = get_supabase()
                    process_completed_work_order(supabase, work_order_id)
                    
                    return jsonify({"status": "processed", "work_order_id": work_order_id})
            
            return jsonify({"status": "skipped"})
            
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500
    
    @app.route("/health", methods=["GET"])
    def health_check():
        return jsonify({"status": "ok", "service": "ml_engine"})
    
    @app.route("/analyze", methods=["POST"])
    def trigger_analysis():
        """Ручной запуск анализа"""
        try:
            supabase = get_supabase()
            analyze_all_equipment(supabase)
            return jsonify({"status": "completed"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    
    return app


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="ML Engine for Railway Maintenance")
    parser.add_argument("--analyze", action="store_true", help="Run full analysis on all equipment")
    parser.add_argument("--work-order", type=str, help="Process specific work order by ID")
    parser.add_argument("--serve", action="store_true", help="Start webhook server")
    parser.add_argument("--port", type=int, default=5000, help="Server port (default: 5000)")
    
    args = parser.parse_args()
    
    supabase = get_supabase()
    
    if args.analyze:
        logger.info("Running full equipment analysis...")
        analyze_all_equipment(supabase)
        
    elif args.work_order:
        logger.info(f"Processing work order: {args.work_order}")
        process_completed_work_order(supabase, args.work_order)
        
    elif args.serve:
        app = create_webhook_app()
        if app:
            logger.info(f"Starting webhook server on port {args.port}...")
            app.run(host="0.0.0.0", port=args.port, debug=False)
        else:
            logger.error("Failed to create Flask app")
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
