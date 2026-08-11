#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Импорт номенклатуры из Excel в Supabase.
- Создаёт записи в departments по именам участков.
- Загружает данные из каждого файла в nomenclature с привязкой к участку.
- Очистка: пустые строки в начале, лишние запятые. Upsert по (department_id, name).
"""
import os
import re
import sys
import time
from pathlib import Path

# Консоль Windows: вывод в UTF-8, чтобы путь "Отчёты ТОИР" и русский текст не падали
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import pandas as pd
from supabase import create_client

BATCH_SIZE = 100  # записей за один запрос — меньше таймаутов

# Участки и привязка файлов
DEPARTMENTS = [
    ("Участок ПТОВ", "#0ea5e9"),
    ("Участок ПТОЛ", "#3b82f6"),
    ("Электровозное депо", "#8b5cf6"),
    ("Участок ВРП", "#22c55e"),
]

FILE_TO_DEPARTMENT = {
    "ПТОВ.xlsx": "Участок ПТОВ",
    "ПТОЛ ТО-2.xlsx": "Участок ПТОЛ",
    "ЭЛ_ДЕПО.xlsx": "Электровозное депо",
    "ВРП.xlsx": "Участок ВРП",
}

# Папка с файлами: excel_folder.txt (UTF-8) > аргумент > env EXCEL_BASE_DIR > по умолчанию
def _get_base_dir():
    script_dir = Path(__file__).resolve().parent
    txt = script_dir / "excel_folder.txt"
    if txt.exists():
        try:
            path = txt.read_text(encoding="utf-8").strip()
            if path:
                return Path(path)
        except Exception:
            pass
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    return Path(os.environ.get("EXCEL_BASE_DIR", r"C:\Users\User\Desktop\Отчёты ТОИР"))
BASE_DIR = _get_base_dir()


def clean_cell(value):
    if isinstance(value, pd.Series):
        value = value.iloc[0] if len(value) > 0 else None
    if pd.isna(value):
        return ""
    s = str(value).strip()
    s = re.sub(r",+", ",", s)
    s = re.sub(r"^,|,$", "", s)
    return s.strip()


def first_non_empty_row_index(df: pd.DataFrame) -> int:
    for i in range(len(df)):
        row = df.iloc[i].astype(str).str.strip()
        if (row != "").any():
            return i
    return len(df)


def infer_name_code_columns(df: pd.DataFrame):
    cols = [c for c in df.columns if isinstance(c, str)]
    name_col = None
    code_col = None
    for c in cols:
        c_lower = str(c).lower().strip()
        if "наименование" in c_lower or "наименомание" in c_lower or "название" in c_lower or c_lower == "name" or "номенклатура" in c_lower or "тмц" in c_lower:
            name_col = c
        if "код" in c_lower or "артикул" in c_lower or c_lower == "code" or c_lower == "№":
            code_col = c
    # Если нашли только код — наименование берём из другого столбца (не подставляем первый столбец как name)
    if name_col is None and code_col is not None and len(cols) >= 2:
        for c in cols:
            if c != code_col:
                name_col = c
                break
    # Часто в Excel: первый столбец = код, второй = наименование. Если оба не распознаны — так и берём.
    if name_col is None and code_col is None and len(cols) >= 2:
        code_col = cols[0]
        name_col = cols[1]
    if name_col is None and len(cols) >= 1:
        name_col = cols[0]
    if code_col is None and len(cols) >= 2:
        code_col = cols[1]
    return name_col, code_col


def load_and_clean_excel(path: Path) -> list[dict]:
    if not path.exists():
        print(f"  Пропуск (файл не найден): {path}")
        return []
    df = pd.read_excel(path, header=None)
    if df.empty:
        return []
    start_idx = first_non_empty_row_index(df)
    df = df.iloc[start_idx:].copy()
    df.columns = [clean_cell(c) for c in df.iloc[0]]
    df = df.iloc[1:].reset_index(drop=True)
    df = df.dropna(how="all")
    name_col, code_col = infer_name_code_columns(df)
    if name_col is None:
        name_col = df.columns[0]
    rows = []
    for _, r in df.iterrows():
        name = clean_cell(r.get(name_col, ""))
        if not name:
            continue
        code = clean_cell(r.get(code_col, "")) if code_col else ""
        extra = {str(k): clean_cell(r.get(k, "")) for k in df.columns if k not in (name_col, code_col)}
        extra = {k: v for k, v in extra.items() if v}
        rows.append({"name": name, "code": code, "extra": extra})
    return rows


def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
    if not url or not key:
        print("Задайте SUPABASE_URL и SUPABASE_SERVICE_KEY (или SUPABASE_ANON_KEY) в .env или окружении")
        return
    supabase = create_client(url, key)

    print("1. Создание/обновление участков (departments)...")
    dept_by_name = {}
    for name, color in DEPARTMENTS:
        existing = supabase.table("departments").select("id").eq("name", name).execute()
        if existing.data and len(existing.data) > 0:
            dept_id = existing.data[0]["id"]
            dept_by_name[name] = dept_id
            print(f"   Обновлён: {name}")
        else:
            # вставка только name (колонка color может отсутствовать в БД)
            ins = supabase.table("departments").insert({"name": name}).execute()
            if ins.data:
                dept_by_name[name] = ins.data[0]["id"]
                print(f"   Создан: {name}")
    if not dept_by_name:
        print("   Не удалось создать участки. Проверьте таблицу departments в Supabase.")
        return

    print("\n2. Импорт номенклатуры из Excel...")
    for filename, dept_name in FILE_TO_DEPARTMENT.items():
        path = BASE_DIR / filename
        dept_id = dept_by_name.get(dept_name)
        if not dept_id:
            continue
        rows = load_and_clean_excel(path)
        if not rows:
            print(f"   {filename}: записей нет")
            continue
        seen = set()
        unique_rows = []
        for r in rows:
            if r["name"] in seen:
                continue
            seen.add(r["name"])
            unique_rows.append(r)

        inserted = 0
        for i in range(0, len(unique_rows), BATCH_SIZE):
            batch = unique_rows[i : i + BATCH_SIZE]
            payloads = [
                {
                    "department_id": dept_id,
                    "name": r["name"],
                    "code": r["code"],
                    "unit": "шт.",
                    "extra": r["extra"],
                }
                for r in batch
            ]
            for attempt in range(3):
                try:
                    supabase.table("nomenclature").upsert(
                        payloads,
                        on_conflict="department_id,name",
                    ).execute()
                    inserted += len(batch)
                    break
                except Exception as e:
                    if attempt < 2 and ("timeout" in str(e).lower() or "timed out" in str(e).lower()):
                        time.sleep(2 * (attempt + 1))
                        continue
                    print(f"   Ошибка батча {i // BATCH_SIZE + 1} ({len(batch)} записей): {e}")
                    for r in batch:
                        try:
                            supabase.table("nomenclature").upsert(
                                {"department_id": dept_id, "name": r["name"], "code": r["code"], "unit": "шт.", "extra": r["extra"]},
                                on_conflict="department_id,name",
                            ).execute()
                            inserted += 1
                        except Exception as e2:
                            print(f"   Ошибка для '{r['name'][:40]}...': {e2}")
                    break
        print(f"   {filename} -> {dept_name}: обработано {inserted} записей (уникальных {len(unique_rows)})")

    print("\nГотово.")


if __name__ == "__main__":
    main()
