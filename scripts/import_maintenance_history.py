"""
Скрипт для импорта истории обслуживания из Excel файлов
Файлы: ПТОВ, ВРП, ЭЛ_ДЕПО, ПТОЛ ТО-2

Требования:
    pip install pandas openpyxl supabase

Запуск:
    python scripts/import_maintenance_history.py

Или с указанием папки:
    python scripts/import_maintenance_history.py --folder "C:\\Users\\User\\Desktop\\Data"
"""

import os
import sys
import argparse
import uuid
from datetime import datetime
from typing import Optional, Dict, List, Any

import pandas as pd
from supabase import create_client, Client

# ═══════════════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════════

SUPABASE_URL = "https://qowgaahijzamnprtfyko.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFvd2dhYWhpanphbW5wcnRmeWtvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE0Njc2MTQsImV4cCI6MjA4NzA0MzYxNH0.zo-bAha0qyNw37yRkitt6f-nF1Gt2hYnanZ5zah-eaA"

# Маппинг имён файлов на названия участков
FILE_TO_SECTION = {
    "ПТОВ": "ПТОВ",
    "ВРП": "ВРП",
    "ЭЛ_ДЕПО": "ЭЛ_ДЕПО",
    "ЭЛ ДЕПО": "ЭЛ_ДЕПО",
    "ЭЛДЕПО": "ЭЛ_ДЕПО",
    "ПТОЛ": "ПТОЛ",
    "ПТОЛ ТО-2": "ПТОЛ",
    "ПТОЛ_ТО-2": "ПТОЛ",
    "ПТОЛ ТО2": "ПТОЛ",
}

# Возможные названия колонок для item_name
ITEM_NAME_COLUMNS = [
    "Наименование номенклатуры",
    "Наименование",
    "Номенклатура",
    "Название",
    "Name",
    "Item",
    "ТМЦ",
    "Материал",
]

# Возможные названия колонок для количества
QTY_COLUMNS = [
    "Количество",
    "Кол-во",
    "Кол.",
    "Qty",
    "Count",
    "Расход",
]

# Возможные названия колонок для единицы измерения
UNIT_COLUMNS = [
    "Единица измерения",
    "Ед. изм.",
    "Ед.изм.",
    "Unit",
    "Единица",
]

# Возможные названия колонок для даты
DATE_COLUMNS = [
    "Дата",
    "Date",
    "Дата ремонта",
    "Дата обслуживания",
    "Дата работ",
]

# Возможные названия колонок для оборудования
EQUIPMENT_COLUMNS = [
    "Оборудование",
    "Локомотив",
    "Вагон",
    "Единица ТПС",
    "Номер",
    "Equipment",
]

# Возможные названия колонок для вида работ
WORK_TYPE_COLUMNS = [
    "Вид работ",
    "Тип работ",
    "Вид ремонта",
    "Ремонт",
    "Work Type",
]


# ═══════════════════════════════════════════════════════════════════════════════
# SUPABASE
# ═══════════════════════════════════════════════════════════════════════════════

def get_supabase_client() -> Client:
    """Создаёт клиент Supabase"""
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def get_departments(supabase: Client) -> Dict[str, str]:
    """Загружает справочник departments и возвращает маппинг name -> id"""
    response = supabase.table("departments").select("id, name").execute()
    if response.data:
        return {d["name"]: d["id"] for d in response.data}
    return {}


def get_sections(supabase: Client) -> Dict[str, str]:
    """Загружает справочник sections и возвращает маппинг name -> id"""
    response = supabase.table("sections").select("id, name").execute()
    if response.data:
        return {s["name"]: s["id"] for s in response.data}
    return {}


def ensure_department_exists(supabase: Client, name: str, dept_map: Dict[str, str]) -> str:
    """Создаёт department если не существует, возвращает id"""
    if name in dept_map:
        return dept_map[name]
    
    # Создаём новый department
    new_id = str(uuid.uuid4())
    response = supabase.table("departments").insert({
        "id": new_id,
        "name": name,
    }).execute()
    
    if response.data:
        dept_map[name] = new_id
        print(f"  ✓ Создан department: {name}")
        return new_id
    
    return ""


def ensure_section_exists(supabase: Client, name: str, section_map: Dict[str, str]) -> str:
    """Создаёт section если не существует, возвращает id"""
    if name in section_map:
        return section_map[name]
    
    # Создаём новый section
    new_id = str(uuid.uuid4())
    response = supabase.table("sections").insert({
        "id": new_id,
        "name": name,
    }).execute()
    
    if response.data:
        section_map[name] = new_id
        print(f"  ✓ Создан section: {name}")
        return new_id
    
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# ЧТЕНИЕ ФАЙЛОВ
# ═══════════════════════════════════════════════════════════════════════════════

def find_column(df: pd.DataFrame, possible_names: List[str]) -> Optional[str]:
    """Ищет колонку по списку возможных названий"""
    df_columns_lower = {col.lower().strip(): col for col in df.columns}
    
    for name in possible_names:
        name_lower = name.lower().strip()
        if name_lower in df_columns_lower:
            return df_columns_lower[name_lower]
        
        # Частичное совпадение
        for col_lower, col_original in df_columns_lower.items():
            if name_lower in col_lower or col_lower in name_lower:
                return col_original
    
    return None


def detect_header_row(df: pd.DataFrame, max_rows: int = 10) -> int:
    """Определяет строку с заголовками"""
    for i in range(min(max_rows, len(df))):
        row = df.iloc[i]
        # Проверяем, есть ли в строке ключевые слова заголовков
        row_str = " ".join(str(v).lower() for v in row.values if pd.notna(v))
        
        keywords = ["наименование", "количество", "дата", "номенклатура", "единица"]
        matches = sum(1 for kw in keywords if kw in row_str)
        
        if matches >= 2:
            return i
    
    return 0


def read_excel_file(filepath: str) -> Optional[pd.DataFrame]:
    """Читает Excel файл, определяя заголовки автоматически"""
    try:
        # Сначала читаем без заголовков
        df_raw = pd.read_excel(filepath, header=None, nrows=15)
        
        # Определяем строку с заголовками
        header_row = detect_header_row(df_raw)
        
        # Читаем с правильными заголовками
        df = pd.read_excel(filepath, header=header_row)
        
        # Убираем пустые строки
        df = df.dropna(how="all")
        
        # Убираем строки где все значения NaN или пустые строки
        df = df[df.apply(lambda row: any(pd.notna(v) and str(v).strip() != "" for v in row), axis=1)]
        
        print(f"  ✓ Прочитано {len(df)} строк (заголовок на строке {header_row + 1})")
        print(f"  Колонки: {list(df.columns)[:5]}...")
        
        return df
        
    except Exception as e:
        print(f"  ✗ Ошибка чтения файла: {e}")
        return None


def extract_section_from_filename(filename: str) -> Optional[str]:
    """Извлекает название участка из имени файла"""
    filename_upper = filename.upper().replace(".XLSX", "").replace(".XLS", "")
    
    for pattern, section in FILE_TO_SECTION.items():
        if pattern.upper() in filename_upper:
            return section
    
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# ОБРАБОТКА ДАННЫХ
# ═══════════════════════════════════════════════════════════════════════════════

def process_dataframe(
    df: pd.DataFrame, 
    section_name: str,
    dept_map: Dict[str, str],
    section_map: Dict[str, str],
    supabase: Client
) -> List[Dict[str, Any]]:
    """Обрабатывает DataFrame и возвращает записи для импорта"""
    
    records = []
    
    # Находим нужные колонки
    item_name_col = find_column(df, ITEM_NAME_COLUMNS)
    qty_col = find_column(df, QTY_COLUMNS)
    unit_col = find_column(df, UNIT_COLUMNS)
    date_col = find_column(df, DATE_COLUMNS)
    equipment_col = find_column(df, EQUIPMENT_COLUMNS)
    work_type_col = find_column(df, WORK_TYPE_COLUMNS)
    
    print(f"  Найденные колонки:")
    print(f"    - Наименование: {item_name_col}")
    print(f"    - Количество:   {qty_col}")
    print(f"    - Ед. изм.:     {unit_col}")
    print(f"    - Дата:         {date_col}")
    print(f"    - Оборудование: {equipment_col}")
    print(f"    - Вид работ:    {work_type_col}")
    
    if not item_name_col:
        print("  ⚠ Колонка 'Наименование номенклатуры' не найдена!")
        return []
    
    # Получаем или создаём department и section
    department_id = ensure_department_exists(supabase, section_name, dept_map)
    section_id = ensure_section_exists(supabase, section_name, section_map)
    
    # Обрабатываем строки
    for idx, row in df.iterrows():
        item_name = str(row.get(item_name_col, "")).strip()
        
        if not item_name or item_name.lower() in ["nan", "none", ""]:
            continue
        
        # Количество
        qty = 0.0
        if qty_col and pd.notna(row.get(qty_col)):
            try:
                qty = float(row[qty_col])
            except (ValueError, TypeError):
                qty = 0.0
        
        # Единица измерения
        unit = "шт."
        if unit_col and pd.notna(row.get(unit_col)):
            unit = str(row[unit_col]).strip() or "шт."
        
        # Дата
        maint_date = None
        if date_col and pd.notna(row.get(date_col)):
            try:
                date_val = row[date_col]
                if isinstance(date_val, datetime):
                    maint_date = date_val.strftime("%Y-%m-%d")
                elif isinstance(date_val, str):
                    # Пробуем разные форматы
                    for fmt in ["%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"]:
                        try:
                            maint_date = datetime.strptime(date_val, fmt).strftime("%Y-%m-%d")
                            break
                        except ValueError:
                            continue
            except Exception:
                pass
        
        # Оборудование
        equipment = ""
        if equipment_col and pd.notna(row.get(equipment_col)):
            equipment = str(row[equipment_col]).strip()
        
        # Вид работ
        work_type = ""
        if work_type_col and pd.notna(row.get(work_type_col)):
            work_type = str(row[work_type_col]).strip()
        
        # Создаём уникальный ID на основе данных (для upsert)
        record_id = f"{section_name}-{item_name[:50]}-{equipment[:20]}-{maint_date or 'nodate'}-{qty}"
        record_id = record_id.replace(" ", "_").replace("/", "_")[:100]
        
        record = {
            "id": record_id,
            "section_id": section_id,
            "section_name": section_name,
            "department_id": department_id,
            "item_name": item_name[:255],
            "qty": qty,
            "unit": unit[:20],
            "equipment": equipment[:100] if equipment else None,
            "work_type": work_type[:100] if work_type else None,
            "maintenance_date": maint_date,
            "created_at": datetime.now().isoformat(),
        }
        
        records.append(record)
    
    return records


# ═══════════════════════════════════════════════════════════════════════════════
# ИМПОРТ В SUPABASE
# ═══════════════════════════════════════════════════════════════════════════════

def create_maintenance_log_table(supabase: Client):
    """
    SQL для создания таблицы maintenance_log (выполнить в Supabase SQL Editor)
    """
    sql = """
-- Таблица истории обслуживания
CREATE TABLE IF NOT EXISTS public.maintenance_log (
    id              text PRIMARY KEY,
    section_id      uuid REFERENCES public.sections(id) ON DELETE SET NULL,
    section_name    text NOT NULL,
    department_id   uuid REFERENCES public.departments(id) ON DELETE SET NULL,
    item_name       text NOT NULL,
    qty             numeric NOT NULL DEFAULT 0,
    unit            text NOT NULL DEFAULT 'шт.',
    equipment       text,
    work_type       text,
    maintenance_date date,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_maintenance_log_section ON public.maintenance_log(section_name);
CREATE INDEX IF NOT EXISTS idx_maintenance_log_item ON public.maintenance_log(item_name);
CREATE INDEX IF NOT EXISTS idx_maintenance_log_date ON public.maintenance_log(maintenance_date);

-- RLS
ALTER TABLE public.maintenance_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY IF NOT EXISTS "maintenance_log_select" ON public.maintenance_log
    FOR SELECT USING (true);

CREATE POLICY IF NOT EXISTS "maintenance_log_insert" ON public.maintenance_log
    FOR INSERT WITH CHECK (true);

CREATE POLICY IF NOT EXISTS "maintenance_log_update" ON public.maintenance_log
    FOR UPDATE USING (true);

CREATE POLICY IF NOT EXISTS "maintenance_log_delete" ON public.maintenance_log
    FOR DELETE USING (true);
"""
    return sql


def import_records(supabase: Client, records: List[Dict[str, Any]], batch_size: int = 100) -> int:
    """Импортирует записи в maintenance_log с использованием upsert"""
    
    if not records:
        return 0
    
    imported = 0
    errors = 0
    
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        
        try:
            response = supabase.table("maintenance_log").upsert(
                batch,
                on_conflict="id"
            ).execute()
            
            imported += len(batch)
            
        except Exception as e:
            print(f"  ⚠ Ошибка при импорте batch {i}-{i+batch_size}: {e}")
            errors += len(batch)
    
    return imported


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def find_files(folder: str) -> List[str]:
    """Ищет файлы Excel с нужными названиями"""
    files = []
    
    if not os.path.exists(folder):
        print(f"✗ Папка не найдена: {folder}")
        return files
    
    for filename in os.listdir(folder):
        if not filename.endswith((".xlsx", ".xls")):
            continue
        
        section = extract_section_from_filename(filename)
        if section:
            files.append(os.path.join(folder, filename))
    
    return files


def main():
    parser = argparse.ArgumentParser(description="Импорт истории обслуживания из Excel")
    parser.add_argument(
        "--folder", 
        type=str, 
        default="C:\\Users\\User\\Desktop",
        help="Папка с Excel файлами"
    )
    parser.add_argument(
        "--files",
        type=str,
        nargs="+",
        help="Конкретные файлы для импорта"
    )
    parser.add_argument(
        "--create-table",
        action="store_true",
        help="Показать SQL для создания таблицы"
    )
    
    args = parser.parse_args()
    
    print("═" * 80)
    print("  ИМПОРТ ИСТОРИИ ОБСЛУЖИВАНИЯ")
    print("  Файлы: ПТОВ, ВРП, ЭЛ_ДЕПО, ПТОЛ ТО-2")
    print("═" * 80)
    
    # Подключение к Supabase
    print("\n→ Подключение к базе данных...")
    supabase = get_supabase_client()
    
    # Показать SQL для создания таблицы
    if args.create_table:
        print("\n" + "─" * 80)
        print("SQL для создания таблицы maintenance_log:")
        print("─" * 80)
        print(create_maintenance_log_table(supabase))
        print("─" * 80)
        print("\nВыполните этот SQL в Supabase SQL Editor перед импортом.")
        return
    
    # Загружаем справочники
    print("\n→ Загрузка справочников...")
    dept_map = get_departments(supabase)
    section_map = get_sections(supabase)
    print(f"  Departments: {len(dept_map)}")
    print(f"  Sections: {len(section_map)}")
    
    # Находим файлы
    if args.files:
        files = args.files
    else:
        print(f"\n→ Поиск файлов в: {args.folder}")
        files = find_files(args.folder)
    
    if not files:
        print("\n✗ Файлы не найдены!")
        print("\nУкажите файлы явно:")
        print('  python scripts/import_maintenance_history.py --files "C:\\path\\ПТОВ.xlsx" "C:\\path\\ВРП.xlsx"')
        print("\nИли укажите папку:")
        print('  python scripts/import_maintenance_history.py --folder "C:\\Users\\User\\Desktop\\Data"')
        print("\nДля создания таблицы в БД:")
        print('  python scripts/import_maintenance_history.py --create-table')
        return
    
    print(f"\n✓ Найдено файлов: {len(files)}")
    for f in files:
        print(f"  • {os.path.basename(f)}")
    
    # Обрабатываем файлы
    all_records = []
    
    for filepath in files:
        filename = os.path.basename(filepath)
        section_name = extract_section_from_filename(filename)
        
        print(f"\n{'─' * 80}")
        print(f"  Обработка: {filename}")
        print(f"  Участок:   {section_name}")
        print(f"{'─' * 80}")
        
        df = read_excel_file(filepath)
        
        if df is None or df.empty:
            print("  ⚠ Файл пустой или не удалось прочитать")
            continue
        
        records = process_dataframe(df, section_name, dept_map, section_map, supabase)
        
        print(f"  ✓ Подготовлено записей: {len(records)}")
        all_records.extend(records)
    
    # Импортируем в БД
    if all_records:
        print(f"\n{'═' * 80}")
        print(f"  ИМПОРТ В БАЗУ ДАННЫХ")
        print(f"{'═' * 80}")
        print(f"\n→ Импорт {len(all_records)} записей...")
        
        try:
            imported = import_records(supabase, all_records)
            print(f"\n✓ Успешно импортировано: {imported} записей")
        except Exception as e:
            print(f"\n✗ Ошибка импорта: {e}")
            print("\nВозможно, таблица maintenance_log не существует.")
            print("Выполните команду для получения SQL:")
            print("  python scripts/import_maintenance_history.py --create-table")
    else:
        print("\n⚠ Нет данных для импорта")
    
    # Итоги
    print(f"\n{'═' * 80}")
    print(f"  ИТОГИ")
    print(f"{'═' * 80}")
    print(f"  Обработано файлов:  {len(files)}")
    print(f"  Всего записей:      {len(all_records)}")
    print(f"  Дата импорта:       {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print(f"{'═' * 80}")


if __name__ == "__main__":
    main()
