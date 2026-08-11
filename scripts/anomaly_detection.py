"""
Скрипт для обнаружения аномалий в расходе запчастей
Использует sklearn.ensemble.IsolationForest для выявления подозрительных ремонтов

Требования:
    pip install pandas numpy scikit-learn supabase python-dotenv tabulate

Запуск:
    python scripts/anomaly_detection.py
"""

import os
import sys
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

# Supabase клиент
from supabase import create_client, Client

# ═══════════════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════════

SUPABASE_URL = "https://qowgaahijzamnprtfyko.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFvd2dhYWhpanphbW5wcnRmeWtvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE0Njc2MTQsImV4cCI6MjA4NzA0MzYxNH0.zo-bAha0qyNw37yRkitt6f-nF1Gt2hYnanZ5zah-eaA"

# Участки для анализа
SECTIONS = ["ПТОВ", "ВРП", "ЭЛ_ДЕПО"]

# Параметры IsolationForest
CONTAMINATION = 0.1  # Ожидаемая доля аномалий (10%)
RANDOM_STATE = 42

# Порог отклонения в сигмах
SIGMA_THRESHOLD = 2.0


# ═══════════════════════════════════════════════════════════════════════════════
# ПОДКЛЮЧЕНИЕ К SUPABASE
# ═══════════════════════════════════════════════════════════════════════════════

def get_supabase_client() -> Client:
    """Создаёт клиент Supabase"""
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ═══════════════════════════════════════════════════════════════════════════════
# ЗАГРУЗКА ДАННЫХ
# ═══════════════════════════════════════════════════════════════════════════════

def load_maintenance_log(supabase: Client) -> pd.DataFrame:
    """
    Загружает данные из таблицы maintenance_log (или work_orders с repair_items)
    Если таблицы maintenance_log нет, используем work_orders
    """
    # Пробуем загрузить maintenance_log
    try:
        response = supabase.table("maintenance_log").select("*").execute()
        if response.data:
            print(f"✓ Загружено {len(response.data)} записей из maintenance_log")
            return pd.DataFrame(response.data)
    except Exception as e:
        print(f"⚠ Таблица maintenance_log не найдена: {e}")
    
    # Fallback: используем work_orders с repair_items
    print("→ Используем данные из work_orders...")
    response = supabase.table("work_orders").select(
        "id, unit, section, repair_kind, status, tech, created_at, repair_items"
    ).execute()
    
    if not response.data:
        print("✗ Нет данных в work_orders")
        return pd.DataFrame()
    
    # Разворачиваем repair_items в отдельные строки
    rows = []
    for wo in response.data:
        repair_items = wo.get("repair_items") or []
        if isinstance(repair_items, list):
            for item in repair_items:
                if isinstance(item, dict):
                    for row in item.get("rows", []):
                        rows.append({
                            "work_order_id": wo["id"],
                            "unit": wo.get("unit", ""),
                            "section": wo.get("section", ""),
                            "repair_kind": wo.get("repair_kind", ""),
                            "status": wo.get("status", ""),
                            "tech": wo.get("tech", ""),
                            "created_at": wo.get("created_at", ""),
                            "item_name": row.get("name", ""),
                            "item_inv_no": row.get("invNo", ""),
                            "item_unit": row.get("unit", "шт."),
                            "item_qty": float(row.get("qty", 0) or 0),
                            "item_note": row.get("note", ""),
                        })
    
    df = pd.DataFrame(rows)
    print(f"✓ Загружено {len(df)} записей расхода ТМЦ из work_orders")
    return df


def load_nomenclature(supabase: Client) -> pd.DataFrame:
    """Загружает справочник номенклатуры с нормативами"""
    response = supabase.table("nomenclature").select(
        "id, name, code, unit, department_id"
    ).execute()
    
    if not response.data:
        print("✗ Нет данных в nomenclature")
        return pd.DataFrame()
    
    # Загружаем departments для маппинга
    dept_response = supabase.table("departments").select("id, name").execute()
    dept_map = {d["id"]: d["name"] for d in (dept_response.data or [])}
    
    df = pd.DataFrame(response.data)
    df["department_name"] = df["department_id"].map(dept_map).fillna("—")
    
    print(f"✓ Загружено {len(df)} позиций номенклатуры")
    return df


def load_sections(supabase: Client) -> pd.DataFrame:
    """Загружает справочник участков"""
    response = supabase.table("sections").select("id, name").execute()
    if response.data:
        return pd.DataFrame(response.data)
    return pd.DataFrame(columns=["id", "name"])


# ═══════════════════════════════════════════════════════════════════════════════
# ПОДГОТОВКА ДАННЫХ
# ═══════════════════════════════════════════════════════════════════════════════

def prepare_data(maintenance_df: pd.DataFrame, nomenclature_df: pd.DataFrame) -> pd.DataFrame:
    """
    Подготавливает данные для анализа:
    - Агрегирует расход по участкам и позициям
    - Рассчитывает нормативы (среднее по всем участкам)
    - Вычисляет отклонения
    """
    if maintenance_df.empty:
        return pd.DataFrame()
    
    # Агрегируем расход по участку и наименованию
    agg_df = maintenance_df.groupby(["section", "item_name"]).agg({
        "item_qty": ["sum", "mean", "std", "count"],
        "work_order_id": "nunique"
    }).reset_index()
    
    # Упрощаем названия колонок
    agg_df.columns = [
        "section", "item_name", 
        "total_qty", "avg_qty", "std_qty", "record_count", "order_count"
    ]
    
    # Заполняем NaN в std нулями
    agg_df["std_qty"] = agg_df["std_qty"].fillna(0)
    
    # Рассчитываем норматив как среднее по всем участкам
    norms = agg_df.groupby("item_name").agg({
        "avg_qty": "mean",
        "std_qty": "mean"
    }).reset_index()
    norms.columns = ["item_name", "norm_avg", "norm_std"]
    
    # Объединяем с нормативами
    result_df = agg_df.merge(norms, on="item_name", how="left")
    
    # Вычисляем отклонение от нормы
    result_df["deviation"] = result_df["avg_qty"] - result_df["norm_avg"]
    result_df["deviation_sigma"] = np.where(
        result_df["norm_std"] > 0,
        result_df["deviation"] / result_df["norm_std"],
        0
    )
    
    # Абсолютное отклонение в процентах
    result_df["deviation_pct"] = np.where(
        result_df["norm_avg"] > 0,
        (result_df["deviation"] / result_df["norm_avg"]) * 100,
        0
    )
    
    return result_df


# ═══════════════════════════════════════════════════════════════════════════════
# ОБНАРУЖЕНИЕ АНОМАЛИЙ
# ═══════════════════════════════════════════════════════════════════════════════

def detect_anomalies_isolation_forest(df: pd.DataFrame) -> pd.DataFrame:
    """
    Использует IsolationForest для обнаружения аномалий
    """
    if df.empty or len(df) < 5:
        print("⚠ Недостаточно данных для IsolationForest")
        return df
    
    # Признаки для модели
    features = ["total_qty", "avg_qty", "deviation", "deviation_pct"]
    X = df[features].fillna(0).values
    
    # Нормализация
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # IsolationForest
    iso_forest = IsolationForest(
        contamination=CONTAMINATION,
        random_state=RANDOM_STATE,
        n_estimators=100
    )
    
    # Предсказание: -1 = аномалия, 1 = норма
    df["anomaly_score"] = iso_forest.fit_predict(X_scaled)
    df["is_anomaly_if"] = df["anomaly_score"] == -1
    
    # Оценка "аномальности" (чем ниже, тем более аномально)
    df["anomaly_decision"] = iso_forest.decision_function(X_scaled)
    
    return df


def detect_anomalies_sigma(df: pd.DataFrame, threshold: float = SIGMA_THRESHOLD) -> pd.DataFrame:
    """
    Обнаружение аномалий по правилу N сигм
    """
    df["is_anomaly_sigma"] = np.abs(df["deviation_sigma"]) > threshold
    return df


def calculate_losses(df: pd.DataFrame, avg_cost_per_unit: float = 50000) -> pd.DataFrame:
    """
    Оценивает убытки от аномального расхода
    avg_cost_per_unit — средняя стоимость единицы ТМЦ (сум)
    """
    # Убыток = отклонение * количество заказов * средняя стоимость
    df["estimated_loss"] = np.where(
        df["deviation"] > 0,  # Перерасход
        df["deviation"] * df["order_count"] * avg_cost_per_unit,
        0
    )
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# ОТЧЁТ
# ═══════════════════════════════════════════════════════════════════════════════

def print_report(df: pd.DataFrame, maintenance_df: pd.DataFrame):
    """Выводит отчёт об аномалиях"""
    
    print("\n" + "═" * 80)
    print("  ОТЧЁТ ОБ АНОМАЛИЯХ В РАСХОДЕ ЗАПЧАСТЕЙ")
    print("═" * 80)
    
    # Фильтруем аномалии
    anomalies = df[df["is_anomaly_if"] | df["is_anomaly_sigma"]].copy()
    
    if anomalies.empty:
        print("\n✓ Аномалий не обнаружено!")
        return
    
    # Сортируем по убыткам
    anomalies = anomalies.sort_values("estimated_loss", ascending=False)
    
    print(f"\n⚠ Обнаружено {len(anomalies)} подозрительных записей\n")
    
    # Статистика по участкам
    print("─" * 80)
    print("  СТАТИСТИКА ПО УЧАСТКАМ")
    print("─" * 80)
    
    for section in anomalies["section"].unique():
        section_data = anomalies[anomalies["section"] == section]
        total_loss = section_data["estimated_loss"].sum()
        print(f"\n  📍 {section}")
        print(f"     Аномальных позиций: {len(section_data)}")
        print(f"     Оценочные убытки:   {total_loss:,.0f} сум")
    
    # Топ-10 подозрительных записей
    print("\n" + "─" * 80)
    print("  ТОП-10 ПОДОЗРИТЕЛЬНЫХ РЕМОНТОВ (по убыткам)")
    print("─" * 80)
    
    top_anomalies = anomalies.head(10)
    
    for i, (_, row) in enumerate(top_anomalies.iterrows(), 1):
        print(f"\n  {i}. {row['item_name'][:50]}")
        print(f"     Участок:           {row['section']}")
        print(f"     Средний расход:    {row['avg_qty']:.2f} (норма: {row['norm_avg']:.2f})")
        print(f"     Отклонение:        {row['deviation']:+.2f} ({row['deviation_pct']:+.1f}%)")
        print(f"     Отклонение (σ):    {row['deviation_sigma']:+.2f}")
        print(f"     Кол-во заказов:    {row['order_count']}")
        print(f"     Оценочные убытки:  {row['estimated_loss']:,.0f} сум")
        
        # Методы обнаружения
        methods = []
        if row["is_anomaly_if"]:
            methods.append("IsolationForest")
        if row["is_anomaly_sigma"]:
            methods.append(f">{SIGMA_THRESHOLD}σ")
        print(f"     Метод обнаружения: {', '.join(methods)}")
    
    # Детализация по конкретным ремонтам
    print("\n" + "─" * 80)
    print("  ДЕТАЛИЗАЦИЯ ПОДОЗРИТЕЛЬНЫХ РЕМОНТОВ")
    print("─" * 80)
    
    if not maintenance_df.empty:
        suspicious_items = anomalies["item_name"].tolist()[:5]
        
        for item_name in suspicious_items:
            item_repairs = maintenance_df[maintenance_df["item_name"] == item_name]
            
            if item_repairs.empty:
                continue
                
            print(f"\n  📦 {item_name[:60]}")
            print(f"     {'─' * 60}")
            
            for _, repair in item_repairs.head(5).iterrows():
                print(f"     • Заказ: {repair.get('work_order_id', '—')[:20]}")
                print(f"       Единица: {repair.get('unit', '—')}, Участок: {repair.get('section', '—')}")
                print(f"       Расход: {repair.get('item_qty', 0)} {repair.get('item_unit', 'шт.')}")
                print(f"       Исполнитель: {repair.get('tech', '—')}")
                print()
    
    # Итоги
    print("═" * 80)
    print("  ИТОГИ")
    print("═" * 80)
    
    total_loss = anomalies["estimated_loss"].sum()
    if_count = anomalies["is_anomaly_if"].sum()
    sigma_count = anomalies["is_anomaly_sigma"].sum()
    
    print(f"\n  Всего аномалий:              {len(anomalies)}")
    print(f"  Обнаружено IsolationForest:  {if_count}")
    print(f"  Обнаружено по правилу {SIGMA_THRESHOLD}σ:   {sigma_count}")
    print(f"  Общие оценочные убытки:      {total_loss:,.0f} сум")
    print(f"\n  Дата анализа: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print("═" * 80)


def export_to_csv(df: pd.DataFrame, filename: str = "anomalies_report.csv"):
    """Экспортирует результаты в CSV"""
    anomalies = df[df["is_anomaly_if"] | df["is_anomaly_sigma"]].copy()
    
    if anomalies.empty:
        print("Нет данных для экспорта")
        return
    
    # Выбираем колонки для экспорта
    export_cols = [
        "section", "item_name", "total_qty", "avg_qty", "norm_avg",
        "deviation", "deviation_pct", "deviation_sigma",
        "order_count", "estimated_loss", "is_anomaly_if", "is_anomaly_sigma"
    ]
    
    export_df = anomalies[export_cols].sort_values("estimated_loss", ascending=False)
    
    filepath = os.path.join(os.path.dirname(__file__), filename)
    export_df.to_csv(filepath, index=False, encoding="utf-8-sig")
    print(f"\n✓ Отчёт сохранён: {filepath}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("═" * 80)
    print("  АНАЛИЗ АНОМАЛИЙ В РАСХОДЕ ЗАПЧАСТЕЙ")
    print("  IsolationForest + Правило N сигм")
    print("═" * 80)
    
    # Подключение к Supabase
    print("\n→ Подключение к базе данных...")
    supabase = get_supabase_client()
    
    # Загрузка данных
    print("\n→ Загрузка данных...")
    maintenance_df = load_maintenance_log(supabase)
    nomenclature_df = load_nomenclature(supabase)
    
    if maintenance_df.empty:
        print("\n✗ Нет данных для анализа!")
        print("  Убедитесь, что в системе есть наряд-задания с заполненными ТМЦ.")
        return
    
    # Фильтрация по участкам (если нужно)
    if SECTIONS:
        available_sections = maintenance_df["section"].unique().tolist()
        print(f"\n→ Доступные участки: {available_sections}")
        
        # Фильтруем только если есть совпадения
        filtered_sections = [s for s in SECTIONS if s in available_sections]
        if filtered_sections:
            maintenance_df = maintenance_df[maintenance_df["section"].isin(filtered_sections)]
            print(f"→ Анализируем участки: {filtered_sections}")
        else:
            print(f"→ Участки {SECTIONS} не найдены, анализируем все данные")
    
    # Подготовка данных
    print("\n→ Подготовка данных для анализа...")
    analysis_df = prepare_data(maintenance_df, nomenclature_df)
    
    if analysis_df.empty:
        print("\n✗ Недостаточно данных для анализа!")
        return
    
    print(f"✓ Подготовлено {len(analysis_df)} агрегированных записей")
    
    # Обнаружение аномалий
    print("\n→ Обнаружение аномалий...")
    
    # Метод 1: IsolationForest
    print("  • IsolationForest...")
    analysis_df = detect_anomalies_isolation_forest(analysis_df)
    
    # Метод 2: Правило N сигм
    print(f"  • Правило {SIGMA_THRESHOLD} сигм...")
    analysis_df = detect_anomalies_sigma(analysis_df)
    
    # Расчёт убытков
    print("  • Оценка убытков...")
    analysis_df = calculate_losses(analysis_df)
    
    # Отчёт
    print_report(analysis_df, maintenance_df)
    
    # Экспорт в CSV
    export_to_csv(analysis_df)


if __name__ == "__main__":
    main()
