"""
Скрипт для заполнения таблицы nomenclature_norms тестовыми данными
Создаёт нормативы расхода ТМЦ для участков ПТОВ, ВРП, ЭЛ_ДЕПО, ПТОЛ

Требования:
    pip install supabase

Запуск:
    python scripts/seed_nomenclature_norms.py
"""

import uuid
from supabase import create_client, Client

# ═══════════════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════════

SUPABASE_URL = "https://qowgaahijzamnprtfyko.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFvd2dhYWhpanphbW5wcnRmeWtvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE0Njc2MTQsImV4cCI6MjA4NzA0MzYxNH0.zo-bAha0qyNw37yRkitt6f-nF1Gt2hYnanZ5zah-eaA"

# Виды работ
WORK_TYPES = ["ТО-1", "ТО-2", "ТО-3", "ТР-1", "ТР-2", "КР"]


def get_supabase_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def main():
    print("=" * 60)
    print("  ZAPOLNENIE NORMATIVOV RASHODA TMC")
    print("=" * 60)
    
    supabase = get_supabase_client()
    
    # Загружаем sections (участки) - используем их ID для нормативов
    print("\n→ Загрузка справочника sections...")
    sect_resp = supabase.table("sections").select("id, name").execute()
    section_map = {s["name"]: s["id"] for s in (sect_resp.data or [])}
    print(f"  Найдено sections: {len(section_map)}")
    for name, sid in section_map.items():
        print(f"    - {name}: {sid}")
    
    # Загружаем nomenclature
    print("\n→ Загрузка справочника nomenclature...")
    nom_resp = supabase.table("nomenclature").select("id, name, code, unit").limit(100).execute()
    nomenclature = nom_resp.data or []
    print(f"  Найдено позиций: {len(nomenclature)}")
    
    if not nomenclature:
        print("\n⚠ Справочник nomenclature пуст!")
        print("  Сначала импортируйте номенклатуру.")
        return
    
    # Генерируем нормативы
    print("\n→ Генерация нормативов...")
    norms = []
    import random
    
    # Используем section_id для привязки нормативов
    for section_name, section_id in section_map.items():
        for work_type in WORK_TYPES:
            # Берём случайные позиции для каждого вида работ
            selected = random.sample(nomenclature, min(10, len(nomenclature)))
            
            for nom in selected:
                # Генерируем случайные нормативы
                std_qty = random.randint(1, 10)
                avg_price = random.randint(10000, 200000)
                
                # Создаём уникальный текстовый ID
                norm_id = f"norm-{section_name}-{work_type}-{nom['id'][:8]}"
                
                norms.append({
                    "id": norm_id,
                    "nomenclature_id": str(nom["id"]),
                    "department_id": str(section_id),  # Используем section_id!
                    "work_type": work_type,
                    "standard_quantity": std_qty,
                    "avg_price": avg_price,
                    "unit": nom.get("unit", "шт."),
                    "note": f"Норматив для {section_name} / {work_type}"
                })
    
    print(f"  Подготовлено нормативов: {len(norms)}")
    
    # Сохраняем в БД
    print("\n→ Сохранение в базу данных...")
    
    try:
        # Используем upsert для избежания дубликатов
        for i in range(0, len(norms), 50):
            batch = norms[i:i+50]
            supabase.table("nomenclature_norms").upsert(
                batch,
                on_conflict="nomenclature_id,department_id,work_type"
            ).execute()
        
        print(f"  ✓ Сохранено {len(norms)} нормативов")
        
    except Exception as e:
        print(f"  ✗ Ошибка: {e}")
        print("\n  Возможно, таблица nomenclature_norms не создана.")
        print("  Выполните SQL из scripts/nomenclature_norms_schema.sql")
    
    # Создаём шаблоны для ТО-2
    print("\n→ Создание шаблонов ТМЦ для ТО-2...")
    
    templates = []
    # Ищем ПТОЛ в sections
    ptol_id = section_map.get("ПТОЛ")
    if ptol_id:
        # Берём первые 5 позиций как шаблон
        for i, nom in enumerate(nomenclature[:5]):
            template_id = f"tpl-PTOL-TO2-{nom['id'][:8]}"
            templates.append({
                "id": template_id,
                "work_type": "ТО-2",
                "department_id": str(ptol_id),  # Используем section_id!
                "nomenclature_id": str(nom["id"]),
                "default_quantity": i + 1,
                "is_required": i < 2,
                "sort_order": i
            })
    else:
        print("  ⚠ Участок ПТОЛ не найден в sections")
    
    if templates:
        try:
            supabase.table("work_type_templates").upsert(
                templates,
                on_conflict="work_type,department_id,nomenclature_id"
            ).execute()
            print(f"  ✓ Создано {len(templates)} шаблонов для ТО-2")
        except Exception as e:
            print(f"  ⚠ Ошибка создания шаблонов: {e}")
    
    print("\n" + "═" * 60)
    print("  ГОТОВО")
    print("═" * 60)


if __name__ == "__main__":
    main()
