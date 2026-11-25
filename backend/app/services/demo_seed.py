"""Demo data for the DEMO copy (database `toir_demo`) only: it fills the sections that are empty in a real copy so every page can be shown.

Safety: refuses to run unless the database name is `toir_demo`, and refuses a second run (it looks for its own employees). Everything it writes is
fictional and is marked: employee tab numbers start with "Д-", nomenclature codes with "ДЕМО-", document numbers with "Д-", notes with "[ДЕМО]".
Real rows (assets, sections, intervals, norms, migration journal) are only READ; the only change to a real row is the asset status (repair /
maintenance) of assets that get an order in progress.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.timeutil import today_local

MARK = "[ДЕМО]"

EMPLOYEES = [
    ("Д-001", "Рахимов Бахтиёр Саидович", "Начальник участка", "ЖДЦ-1"),
    ("Д-002", "Каримов Олимжон Абдуллаевич", "Мастер", "ЖДЦ-1"),
    ("Д-003", "Исмоилов Шерзод Рустамович", "Бригадир", "ЖДЦ-1"),
    ("Д-004", "Юлдашев Азамат Тулкинович", "Слесарь по ремонту подвижного состава", "ЖДЦ-1"),
    ("Д-005", "Петров Андрей Викторович", "Слесарь по ремонту подвижного состава", "ЖДЦ-1"),
    ("Д-006", "Назаров Дилшод Ахмедович", "Электромонтёр", "ЖДЦ-1"),
    ("Д-007", "Султанов Жасур Муродович", "Начальник участка", "ЖДЦ-2"),
    ("Д-008", "Ахмедов Равшан Каюмович", "Мастер", "ЖДЦ-2"),
    ("Д-009", "Ким Сергей Владимирович", "Бригадир", "ЖДЦ-2"),
    ("Д-010", "Тошматов Улугбек Насимович", "Слесарь по ремонту подвижного состава", "ЖДЦ-2"),
    ("Д-011", "Иванов Дмитрий Олегович", "Слесарь-ремонтник", "ЖДЦ-2"),
    ("Д-012", "Хамидов Фаррух Баходирович", "Машинист-инструктор", "ЖДЦ-2"),
    ("Д-013", "Мирзаев Анвар Собирович", "Инженер ПТО", "ЖДЦ-1"),
    ("Д-014", "Абдуллаева Малика Равшановна", "Инженер ПТО", "ЖДЦ-2"),
    ("Д-015", "Шарипов Бекзод Икромович", "Кладовщик", "ЖДЦ-1"),
    ("Д-016", "Козлова Елена Павловна", "Кладовщик", "ЖДЦ-2"),
]

# (name, unit, price UZS, kind) kind: loco | wagon | both
NOMENCLATURE = [
    ("Масло моторное М-14Г2ЦС", "кг", 21500, "loco"), ("Масло индустриальное И-20А", "кг", 14800, "loco"), ("Масло компрессорное", "кг", 19800, "loco"),
    ("Фильтр топливный тонкой очистки", "шт", 185000, "loco"), ("Фильтр масляный дизеля", "шт", 240000, "loco"), ("Фильтр воздушный", "шт", 132000, "loco"),
    ("Подшипник буксовый роликовый", "шт", 1250000, "both"), ("Втулка цилиндровая", "шт", 3400000, "loco"), ("Кольца поршневые (комплект)", "компл", 980000, "loco"),
    ("Прокладка головки цилиндра", "шт", 76000, "loco"), ("Форсунка топливная", "шт", 1650000, "loco"), ("Щётка электрическая ЭГ-14", "шт", 38000, "loco"),
    ("Лампа прожекторная 75 Вт", "шт", 24000, "loco"), ("Кабель силовой ПВ-3 (м)", "м", 41000, "loco"), ("Манжета тормозного цилиндра", "шт", 18500, "both"),
    ("Колодка тормозная композиционная", "шт", 156000, "both"), ("Колодка тормозная чугунная", "шт", 98000, "both"), ("Смазка Буксол", "кг", 32000, "both"),
    ("Смазка ЖРО", "кг", 27500, "wagon"), ("Клин фрикционный", "шт", 210000, "wagon"), ("Пружина рессорного подвешивания", "шт", 340000, "wagon"),
    ("Поглощающий аппарат Ш-2-В", "шт", 2850000, "wagon"), ("Корпус автосцепки СА-3", "шт", 3900000, "wagon"), ("Триангель", "шт", 520000, "wagon"),
    ("Авторежим 265А-1", "шт", 780000, "wagon"), ("Кран разобщительный 372", "шт", 145000, "both"), ("Рукав соединительный Р17Б", "шт", 96000, "both"),
    ("Воздухораспределитель 483М", "шт", 1450000, "wagon"), ("Болт М20х80", "шт", 4200, "both"), ("Гайка М20", "шт", 1900, "both"),
    ("Шплинт 5х50", "шт", 600, "both"), ("Электроды сварочные УОНИ 13/55", "кг", 31000, "both"), ("Краска эмаль ПФ-115", "кг", 38000, "both"),
    ("Ветошь обтирочная", "кг", 9000, "both"), ("Растворитель Р-4", "л", 16000, "both"), ("Диск отрезной 230 мм", "шт", 14000, "both"),
    ("Резиновое уплотнение крышки люка", "м", 52000, "wagon"), ("Сурик железный", "кг", 27000, "wagon"), ("Прокладка паронитовая", "кг", 64000, "both"),
]

SUBTASKS = {
    "ТО-1": ["Внешний осмотр", "Проверка уровней масла и воды", "Проверка тормозной системы", "Проверка освещения и сигнализации", "Запись в журнал"],
    "ТО-2": ["Внешний осмотр и очистка", "Замена масла и фильтров по норме", "Проверка тормозной рычажной передачи", "Проверка электрических цепей", "Проверка экипажной части", "Запись в журнал"],
    "ТО-3": ["Осмотр дизеля и вспомогательных агрегатов", "Замена масла, топливных и воздушных фильтров", "Проверка и регулировка тормозов", "Осмотр тяговых двигателей и щёточного аппарата", "Проверка буксовых узлов", "Испытание и обкатка"],
    "ТР-1": ["Частичная разборка узлов", "Осмотр и измерение износов", "Замена изношенных деталей", "Ремонт тормозного оборудования", "Сборка и регулировка", "Испытание под нагрузкой"],
    "ТР-2": ["Разборка узлов", "Дефектоскопия ответственных деталей", "Ремонт тележек и колёсных пар", "Ремонт дизеля и агрегатов", "Сборка", "Испытание и приёмка"],
    "ТР-3": ["Полная разборка узлов", "Дефектоскопия и обмер деталей", "Ремонт дизеля, ТЭД, тележек", "Замена по норме расхода материалов", "Сборка и регулировка", "Реостатные испытания", "Приёмка комиссией"],
    "СР": ["Подготовка к ремонту", "Разборка и дефектация", "Восстановление деталей", "Сборка", "Испытания", "Окраска и приёмка"],
    "КР": ["Постановка в ремонт и разборка", "Дефектация всех узлов", "Капитальный ремонт дизеля и ТЭД", "Ремонт кузова и рамы", "Сборка", "Испытания", "Окраска, приёмка, паспорт"],
    "КР-2": ["Постановка в ремонт и разборка", "Дефектация всех узлов", "Капитальный ремонт агрегатов", "Ремонт кузова и рамы", "Сборка", "Испытания и приёмка"],
    "ВНП": ["Внеплановый осмотр", "Установление причины", "Устранение неисправности", "Проверка после ремонта"],
    "ТО-1В": ["Осмотр ходовых частей", "Проверка автосцепки", "Проверка тормозов", "Отметка в журнале"],
    "ТО-2В": ["Осмотр кузова и рамы", "Проверка буксовых узлов", "Проверка тормозного оборудования", "Проверка автосцепного устройства", "Отметка в журнале"],
    "ТОР": ["Отцепка и постановка на путь ремонта", "Устранение неисправности", "Проверка тормозов", "Выпуск из ремонта"],
    "ТОВ": ["Осмотр кузова", "Проверка разгрузочного механизма", "Проверка ходовых частей", "Проверка тормозов", "Отметка в журнале"],
    "ДР": ["Подкатка и разборка", "Дефектация колёсных пар и тележек", "Ремонт автосцепки и поглощающего аппарата", "Ремонт тормозной системы", "Сборка", "Испытания и приёмка"],
    "КРВ": ["Разборка вагона", "Капитальный ремонт кузова", "Ремонт тележек и колёсных пар", "Ремонт тормозной системы", "Сборка", "Окраска", "Приёмка"],
    "ВНВ": ["Осмотр", "Устранение неисправности", "Проверка"],
}
DEFAULT_HOURS = {"ТО-1": 4, "ТО-2": 12, "ТО-3": 24, "ТР-1": 48, "ТР-2": 96, "ТР-3": 168, "СР": 240, "КР": 480, "КР-2": 480, "ВНП": 16,
                 "ТО-1В": 2, "ТО-2В": 4, "ТОР": 8, "ТОВ": 3, "ДР": 72, "КРВ": 240, "ВНВ": 6}

DISRUPTIONS = [
    ("parts", "section", "ЖДЦ-1", 6, 2, "Нет тормозных колодок на складе, ждём поставку"),
    ("no_bay", "section", "ЖДЦ-2", 14, 9, "Канава №2 на ремонте, постановка тепловозов перенесена"),
    ("no_crew", "section", "ЖДЦ-1", 3, None, "Нехватка слесарей: отпуска и больничные"),
    ("unit_unavailable", "asset", None, 8, 3, "Тепловоз занят на маневровой работе, в ремонт не поставлен"),
    ("accident", "asset", None, 11, 5, "Повреждение после столкновения на путях, ждём комиссию"),
    ("weather", "all", None, 20, 18, "Сильный ветер и снег, наружные работы остановлены"),
    ("sensor_failure", "section", "ЖДЦ-2", 5, None, "Датчики пробега давали сбои, данные уточняются"),
    ("unplanned_repair", "asset", None, 4, None, "Внеплановый ремонт сорвал плановое ТО"),
    ("other", "all", None, 30, 28, "Плановое отключение электроэнергии"),
]


def _ts(base: datetime, **delta: float) -> datetime:
    return base + timedelta(**delta)


async def _one(db: AsyncSession, sql: str, **p: Any) -> Any:
    return (await db.execute(text(sql), p)).scalar_one_or_none()


async def seed(db: AsyncSession) -> dict[str, int]:
    if settings.postgres_db != "toir_demo":
        raise ValueError(f"Refused: the demo data goes only into the database 'toir_demo' (this one is '{settings.postgres_db}')")
    if await _one(db, "select 1 from employees where tab_number like 'Д-%' limit 1"):
        raise ValueError("The demo data is already loaded (employees 'Д-…' exist)")
    rng = random.Random(20261125)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    today = today_local()
    counts: dict[str, int] = {}

    sections = {r.name: r.id for r in (await db.execute(text("select id, name from sections"))).all()}
    departments = {r.name: r.id for r in (await db.execute(text("select id, name from departments"))).all()}
    wt = {r.code: (r.id, r.unit_type, r.duration_hours) for r in (await db.execute(text("select id, code, unit_type, duration_hours from work_types"))).all()}

    # КР-2 is a locomotive repair kind of its own (the locomotive norm files are for it); the main system gets it by hand
    if "КР-2" not in wt:
        order = await _one(db, "select coalesce(max(sort_order),0)+1 from work_types")
        wid = await _one(db, "insert into work_types (code, name, unit_type, sort_order) values ('КР-2', 'КР-2', 'locomotive', :o) returning id", o=order)
        wt["КР-2"] = (wid, "locomotive", None)
        counts["work_types_added"] = 1
    # durations the demo can show (only where empty)
    for code, hours in DEFAULT_HOURS.items():
        await db.execute(text("update work_types set duration_hours=:h where code=:c and duration_hours is null"), {"h": hours, "c": code})

    # ---- employees
    emp_by_section: dict[str, list[Any]] = {"ЖДЦ-1": [], "ЖДЦ-2": []}
    chiefs: dict[str, Any] = {}
    for tab, name, position, sec in EMPLOYEES:
        eid = await _one(db, "insert into employees (tab_number, full_name, position, section_id, is_active) values (:t,:n,:p,:s,true) returning id", t=tab, n=name, p=position, s=sections[sec])
        emp_by_section[sec].append((eid, name, position))
        if position == "Начальник участка":
            chiefs[sec] = (eid, name)
    counts["employees"] = len(EMPLOYEES)

    # ---- nomenclature, norms, templates, subtasks
    dept_for = {"loco": ["Участок ПТОЛ", "Электровозное депо"], "wagon": ["Участок ПТОВ", "Участок ВРП"]}
    nom: dict[str, list[dict[str, Any]]] = {d: [] for d in departments}
    code_no = 0
    for dept_name, dept_id in departments.items():
        is_loco = dept_name in dept_for["loco"]
        for name, unit, price, kind in NOMENCLATURE:
            if kind != "both" and (kind == "loco") != is_loco:
                continue
            code_no += 1
            nid = await _one(db, "insert into nomenclature (department_id, name, code, unit, extra) values (:d,:n,:c,:u,CAST(:x AS jsonb)) returning id",
                             d=dept_id, n=name, c=f"ДЕМО-{code_no:04d}", u=unit, x=json.dumps({"demo": True, "price": price}))
            nom[dept_name].append({"id": nid, "name": name, "unit": unit, "price": price})
    counts["nomenclature"] = code_no

    templates: dict[tuple[str, str], list[dict[str, Any]]] = {}
    n_norm = n_tpl = 0
    for dept_name, items in nom.items():
        is_loco = dept_name in dept_for["loco"]
        for code, (wid, unit_type, _h) in wt.items():
            if (unit_type == "locomotive") != is_loco:
                continue
            heavy = code in ("ТР-2", "ТР-3", "СР", "КР", "КР-2", "ДР", "КРВ")
            chosen = rng.sample(items, k=min(len(items), rng.randint(7, 11) if heavy else rng.randint(3, 6)))
            lst = []
            for it in chosen:
                qty = round(rng.uniform(1, 40 if it["unit"] in ("кг", "л", "м") else 8) * (2.5 if heavy else 1), 1)
                if it["unit"] in ("шт", "компл") and qty < 1:
                    qty = 1
                await db.execute(text(
                    "insert into nomenclature_norms (nomenclature_id, department_id, work_type_id, standard_quantity, avg_price, min_quantity, max_quantity) "
                    "values (:n,:d,:w,:q,:p,:mn,:mx) on conflict do nothing"),
                    {"n": it["id"], "d": departments[dept_name], "w": wid, "q": qty, "p": it["price"], "mn": round(qty * 0.7, 1), "mx": round(qty * 1.4, 1)})
                n_norm += 1
                await db.execute(text(
                    "insert into work_type_templates (work_type_id, department_id, nomenclature_id, name, unit, default_quantity, is_required, note) "
                    "values (:w,:d,:n,:nm,:u,:q,:r,:note)"),
                    {"w": wid, "d": departments[dept_name], "n": it["id"], "nm": it["name"], "u": it["unit"], "q": qty, "r": rng.random() < 0.6, "note": MARK})
                n_tpl += 1
                lst.append({**it, "qty": qty})
            templates[(code, dept_name)] = lst
    counts["nomenclature_norms"], counts["work_type_templates"] = n_norm, n_tpl

    n_sub = 0
    for code, steps in SUBTASKS.items():
        if code not in wt:
            continue
        has = await _one(db, "select 1 from work_subtasks where work_type_id=:w limit 1", w=wt[code][0])
        if has:
            continue
        for i, step in enumerate(steps, start=1):
            await db.execute(text("insert into work_subtasks (work_type_id, name, sort_order) values (:w,:n,:s)"), {"w": wt[code][0], "n": step, "s": i})
            n_sub += 1
    counts["work_subtasks"] = n_sub

    # ---- assets to work on
    assets = (await db.execute(text(
        "select a.id, a.inv_number, a.asset_type, a.section_id, a.mileage, s.name as section, m.name as model from fixed_assets a "
        "join sections s on s.id=a.section_id left join asset_models m on m.id=a.model_id where a.status='operational' and a.decommissioned_at is null"))).all()
    loco_assets = [a for a in assets if a.asset_type in ("diesel", "locomotive")]
    wagon_assets = [a for a in assets if a.asset_type not in ("diesel", "locomotive")]
    rng.shuffle(loco_assets)
    rng.shuffle(wagon_assets)
    pool_loco, pool_wagon = loco_assets[:80], wagon_assets[:260]

    DAYS = 240  # about 8 months of work history
    TOTAL_ORDERS = 720
    MAX_IN_PROGRESS = 30
    loco_codes = {"planned": ["ТО-1"] * 4 + ["ТО-2"] * 3 + ["ТО-3"] * 2 + ["ТР-1"], "unplanned": ["ВНП", "ТО-2"], "repair": ["ТР-1"] * 3 + ["ТР-2"] * 3 + ["ТР-3"] * 2 + ["СР", "КР-2"], "emergency": ["ВНП", "ТР-1"]}
    wagon_codes = {"planned": ["ТО-1В"] * 3 + ["ТО-2В"] * 2 + ["ТОВ"] * 2, "unplanned": ["ТОР", "ВНВ"], "repair": ["ДР"] * 3 + ["ТОР"] * 2 + ["КРВ"], "emergency": ["ТОР", "ВНВ"]}
    kinds = ["planned"] * 12 + ["unplanned"] * 3 + ["repair"] * 5 + ["emergency"]
    priorities = {"planned": ["normal", "normal", "low"], "unplanned": ["normal", "high"], "repair": ["high", "normal", "normal"], "emergency": ["critical", "high"]}
    wh = ["Склад №1 (ЖДЦ-1)", "Склад №2 (ЖДЦ-2)", "Центральный склад ТМЦ"]
    weak_names = {"Петров Андрей Викторович", "Иванов Дмитрий Олегович"}  # the "human factor" scenarios go to these two

    SCENARIOS = {  # name: weight
        "late_start": 22, "overrun_time": 18, "tmc_overuse": 22, "accident": 10, "repeat": 10, "human_wrong": 8, "human_unclosed": 5, "human_nodocs": 5}
    ACCIDENTS = ["Столкновение на манёвровых путях, повреждение рамы и автосцепки", "Сход с рельсов на стрелочном переводе", "Пожар в машинном отделении, устранение последствий",
                 "Наезд на препятствие, повреждение тормозного оборудования", "Несчастный случай при расцепке: простой до окончания расследования"]
    HUMAN = ["Ошибка исполнителя: неверно подобран ТМЦ, пришлось переделывать", "Нарушена технология сборки, замечание комиссии", "Пропущена операция по чек-листу, найдено при приёмке"]
    UNCLOSED = "Наряд не закрыт исполнителем: работы окончены, отметки нет"
    NODOCS = "Ремонт закрыт без списания ТМЦ: нет требования-накладной"

    st = {"orders": 0, "items": 0, "docs": 0, "doc_items": 0, "log": 0, "inprog": 0}
    used_numbers: set[str] = set()
    in_progress_assets: list[tuple[Any, str]] = []
    problems: list[dict[str, Any]] = []

    async def make_order(a: Any, code: str, kind: str, age_days: int, *, status: str | None = None, scenario: str | None = None, text_note: str = "",
                         desc_override: str | None = None, hours_factor: float | None = None, delay_h: float | None = None, over_items: float | None = None,
                         no_items: bool = False, weak: bool = False, priority: str | None = None) -> dict[str, Any] | None:
        if code not in wt:
            return None
        is_loco = a.asset_type in ("diesel", "locomotive")
        sec = a.section if a.section in emp_by_section else "ЖДЦ-1"
        created = _ts(now, days=-age_days, hours=-rng.randint(0, 20) if age_days else -rng.randint(0, 3))
        hours = float(wt[code][2] or DEFAULT_HOURS.get(code, 8))
        start = created + timedelta(hours=rng.randint(1, 12))
        end = start + timedelta(hours=hours)
        if status is None:
            if age_days > 6:
                status = rng.choices(["completed", "cancelled"], [95, 5])[0]
            elif age_days > 1:
                status = rng.choices(["completed", "in_progress", "pending"], [70, 20, 10])[0]
            else:
                status = rng.choices(["in_progress", "pending", "completed"], [55, 35, 10])[0]
        if status == "in_progress" and scenario != "human_unclosed":
            if st["inprog"] >= MAX_IN_PROGRESS:
                status = "completed" if age_days > 0 else "pending"
        if status == "in_progress":
            st["inprog"] += 1
        d = delay_h if delay_h is not None else rng.uniform(0, 3)
        actual_start = actual_end = closed_at = None
        if status in ("in_progress", "completed"):
            actual_start = min(now - timedelta(hours=1), start + timedelta(hours=d))
        if status == "completed":
            duration = hours * (hours_factor if hours_factor is not None else rng.uniform(0.75, 1.05))
            actual_end = actual_start + timedelta(hours=duration)
            if actual_end > now - timedelta(minutes=30):
                actual_end = now - timedelta(minutes=30)
                actual_start = actual_end - timedelta(hours=duration)
            closed_at = actual_end
        if status == "cancelled":
            closed_at = start
        number = f"НЗ-{created.strftime('%Y%m%d-%H%M%S')}"
        while number in used_numbers:
            created += timedelta(seconds=1)
            number = f"НЗ-{created.strftime('%Y%m%d-%H%M%S')}"
        used_numbers.add(number)
        dept_name = ("Электровозное депо" if a.asset_type == "locomotive" else "Участок ПТОЛ") if is_loco else ("Участок ВРП" if code in ("ДР", "КРВ") else "Участок ПТОВ")
        execs = [e for e in emp_by_section[sec] if "Слесарь" in e[2] or "Бригадир" in e[2] or "Мастер" in e[2]]
        if weak:
            weak_execs = [e for e in emp_by_section[sec] if e[1] in weak_names] or [e for e in emp_by_section["ЖДЦ-1"] if e[1] in weak_names]
            execs = weak_execs or execs
        executor = rng.choice(execs)
        chief = chiefs[sec]
        model = f" {a.model}" if a.model else ""
        what = {"planned": "плановое обслуживание", "unplanned": "внеплановые работы", "repair": "ремонт по графику", "emergency": "аварийное устранение неисправности"}[kind]
        desc = desc_override or f"{code}{model} № {a.inv_number}: {what}"
        daily = rng.uniform(90, 230) if is_loco else rng.uniform(70, 190)
        mileage_then = max(0.0, float(a.mileage or 0) - age_days * daily)
        oid = await _one(db, (
            "insert into work_orders (number, fixed_asset_id, section_id, department_id, order_kind, status, priority, executor_id, chief_id, description, note, "
            "date_start, date_end, closed_at, mileage_at_creation, actual_start, actual_end, created_at, updated_at) "
            "values (:num,:a,:s,:d,:k,:st,:pr,:ex,:ch,:ds,:nt,:dstart,:dend,:cl,:mil,:astart,:ae,:cr,:cr) returning id"),
            num=number, a=a.id, s=a.section_id, d=departments[dept_name], k=kind, st=status, pr=priority or rng.choice(priorities[kind]), ex=executor[0], ch=chief[0], ds=desc,
            nt=f"{MARK} {text_note}".strip(), dstart=start, dend=end, cl=closed_at, mil=round(mileage_then, 2), astart=actual_start, ae=actual_end, cr=created)
        st["orders"] += 1
        rid = await _one(db, "insert into work_order_repairs (work_order_id, work_type_id, sort_order) values (:o,:w,0) returning id", o=oid, w=wt[code][0])
        tpl = templates.get((code, dept_name)) or []
        picked = [] if no_items else (rng.sample(tpl, k=min(len(tpl), rng.randint(2, 5))) if tpl else [])
        doc_items = []
        for j, it in enumerate(picked):
            factor = rng.uniform(0.7, 0.95)
            if over_items and j < 2:
                factor = over_items * rng.uniform(0.95, 1.1)
            qty = max(0.1, round(it["qty"] * factor, 1))
            await db.execute(text("insert into work_order_items (repair_id, nomenclature_id, name, unit, qty, note, sort_order) values (:r,:n,:nm,:u,:q,:nt,:s)"),
                             {"r": rid, "n": it["id"], "nm": it["name"], "u": it["unit"], "q": qty, "nt": MARK, "s": j})
            st["items"] += 1
            doc_items.append((it, qty))
        if status == "in_progress":
            in_progress_assets.append((a.id, kind))
        if status == "completed" and doc_items:
            ddate = closed_at.astimezone(timezone.utc).date()
            dstat = "closed" if (today - ddate).days > 7 else rng.choice(["issued", "closed", "draft"])
            st["docs"] += 1
            did = await _one(db, (
                "insert into tmc_documents (doc_no, doc_date, work_order_id, section_id, work_type_id, warehouse, issued_by, accepted_by, chief, status, created_at) "
                "values (:no,:dd,:o,:s,:w,:wh,:ib,:ab,:ch,:st,:cr) returning id"),
                no=f"Д-{st['docs']:04d}", dd=ddate, o=oid, s=a.section_id, w=wt[code][0], wh=wh[0 if sec == "ЖДЦ-1" else 1],
                ib=[e for e in emp_by_section[sec] if e[2] == "Кладовщик"][0][1], ab=executor[1], ch=chief[1], st=dstat, cr=closed_at)
            for j, (it, qty) in enumerate(doc_items):
                await db.execute(text("insert into tmc_document_items (document_id, nomenclature_id, name, unit, qty, price, note, sort_order) values (:d,:n,:nm,:u,:q,:p,:nt,:s)"),
                                 {"d": did, "n": it["id"], "nm": it["name"], "u": it["unit"], "q": qty, "p": it["price"], "nt": MARK if j == 0 else None, "s": j})
                st["doc_items"] += 1
                await db.execute(text("insert into maintenance_log (section_id, item_name, qty, unit, equipment, work_type, maintenance_date) values (:s,:i,:q,:u,:e,:w,:d)"),
                                 {"s": a.section_id, "i": it["name"], "q": qty, "u": it["unit"], "e": a.inv_number, "w": code, "d": ddate})
                st["log"] += 1
        return {"id": oid, "number": number, "status": status, "created": created, "closed_at": closed_at, "executor": executor[1], "code": code, "asset": a, "age": age_days}

    def problem(info: dict[str, Any] | None, scenario: str, severity: str, itype: str, message: str, action: str, **details: Any) -> None:
        if info:
            problems.append({"info": info, "scenario": scenario, "severity": severity, "type": itype, "message": message, "action": action, "details": details})

    for _ in range(TOTAL_ORDERS):
        is_loco = rng.random() < 0.42
        a = rng.choice(pool_loco if is_loco else pool_wagon)
        kind = rng.choice(kinds)
        code = rng.choice((loco_codes if is_loco else wagon_codes)[kind])
        age = rng.randint(0, 5) if rng.random() < 0.09 else int(DAYS * rng.random())
        scen = rng.choices(list(SCENARIOS), list(SCENARIOS.values()))[0] if rng.random() < 0.12 else None
        label = f"{a.inv_number}"
        if scen == "late_start":
            late = rng.uniform(1.5, 5.0)
            info = await make_order(a, code, kind, max(age, 6), status="completed", scenario=scen, delay_h=late * 24,
                                    text_note=f"Не вошёл в ремонт вовремя: опоздание {late:.1f} сут.")
            problem(info, scen, "high" if late > 3 else "medium", "efficiency", f"{label}: не вошёл в ремонт {code} вовремя, опоздание {late:.1f} сут. Плановое ТО сорвано",
                    "Проверить причину (канава, материалы, люди) и согласовать перенос", delay_days=round(late, 1))
        elif scen == "overrun_time":
            factor = rng.uniform(1.8, 3.0)
            info = await make_order(a, code, kind, max(age, 6), status="completed", scenario=scen, hours_factor=factor,
                                    text_note=f"Простой в ремонте в {factor:.1f} раза дольше нормы")
            problem(info, scen, "high", "efficiency", f"{label}: {code} занял в {factor:.1f} раза больше нормативного времени",
                    "Разобрать причину задержки с мастером участка", time_factor=round(factor, 2))
        elif scen == "tmc_overuse":
            factor = rng.uniform(1.9, 3.2)
            info = await make_order(a, code, kind, max(age, 6), status="completed", scenario=scen, over_items=factor,
                                    text_note=f"Перерасход ТМЦ: до {factor:.1f} раза выше нормы")
            problem(info, scen, "high" if factor > 2.5 else "medium", "anomaly", f"{label}: перерасход ТМЦ при {code}, до {factor:.1f} раза выше нормы. Лишний расход",
                    "Проверить списание и остатки, запросить объяснение исполнителя", over_factor=round(factor, 2))
        elif scen == "accident":
            ac = rng.choice(ACCIDENTS)
            info = await make_order(a, "ВНП" if is_loco else "ТОР", "emergency", max(age, 8), status="completed", scenario=scen, priority="critical", hours_factor=rng.uniform(1.5, 2.5),
                                    over_items=rng.uniform(1.3, 2.0), desc_override=f"{ac} ({label})", text_note="Авария / происшествие")
            problem(info, scen, "critical", "anomaly", f"{label}: аварийная ситуация. {ac}", "Назначить комиссию, проверить соседнюю технику и график ТО", accident=True)
        elif scen == "repeat":
            first = await make_order(a, code, kind, max(age, 25), status="completed", scenario=scen, text_note="После ремонта отказ повторился")
            gap = rng.randint(6, 18)
            if first:
                second = await make_order(a, "ВНП" if is_loco else "ВНВ", "unplanned", max(first["age"] - gap, 0), scenario=scen, priority="high",
                                          desc_override=f"Повторный отказ {label} через {gap} сут. после {code}", text_note=f"Повторный ремонт через {gap} сут.")
                problem(second, scen, "high", "efficiency", f"{label}: повторный отказ через {gap} сут. после {code}. Возможен брак ремонта", "Проверить качество предыдущего ремонта", gap_days=gap)
        elif scen == "human_wrong":
            txt = rng.choice(HUMAN)
            info = await make_order(a, code, kind, max(age, 6), status="completed", scenario=scen, weak=True, over_items=rng.uniform(1.5, 2.2), hours_factor=rng.uniform(1.3, 1.9), text_note=txt)
            problem(info, scen, "medium", "anomaly", f"{label}: человеческий фактор. {txt}", "Провести разбор и инструктаж исполнителя", human_factor=True)
        elif scen == "human_unclosed" and sum(1 for p in problems if p["scenario"] == "human_unclosed") < 5:
            info = await make_order(a, code, kind, rng.randint(22, 55), status="in_progress", scenario=scen, weak=True, text_note=UNCLOSED, desc_override=f"{code} № {label}: {UNCLOSED}")
            problem(info, scen, "high", "efficiency", f"{label}: наряд открыт уже {info['age'] if info else 0} сут., техника в ремонте без движения. Возможно, забыли закрыть", "Проверить фактическое состояние и закрыть наряд", human_factor=True)
        elif scen == "human_nodocs":
            info = await make_order(a, code, kind, max(age, 6), status="completed", scenario=scen, no_items=True, weak=True, text_note=NODOCS)
            problem(info, scen, "medium", "anomaly", f"{label}: {code} закрыт без списания ТМЦ. Расход не подтверждён документами", "Оформить требование-накладную", human_factor=True)
        else:
            await make_order(a, code, kind, age)
    counts.update(work_orders=st["orders"], work_order_items=st["items"], tmc_documents=st["docs"], tmc_document_items=st["doc_items"], maintenance_log=st["log"], problem_orders=len(problems))

    # assets with an order in progress show as in repair / maintenance on the dashboard
    changed = 0
    for aid, kind in sorted({x[0]: x for x in in_progress_assets}.values(), key=lambda x: str(x[0])):
        r = await db.execute(text("update fixed_assets set status=:s where id=:i and status='operational'"), {"s": "maintenance" if kind in ("planned", "unplanned") else "repair", "i": aid})
        changed += r.rowcount or 0
    counts["assets_status_changed"] = changed

    # ---- reliability figures of the fleet (feed the health charts): mostly healthy, some warning, few at risk
    fleet = (await db.execute(text("select id, asset_type from fixed_assets where asset_type in ('locomotive','diesel','wagon') and decommissioned_at is null"))).all()
    risk: list[tuple[Any, float]] = []
    health_rows = []
    for fa in fleet:
        x = rng.random()
        fp = rng.uniform(0.02, 0.18) if x < 0.8 else rng.uniform(0.2, 0.48) if x < 0.94 else rng.uniform(0.5, 0.78) if x < 0.99 else rng.uniform(0.8, 0.92)
        health_rows.append({"i": fa.id, "f": round(fp, 4), "h": round(100 * (1 - fp) * rng.uniform(0.93, 1.0), 2)})
        if fp >= 0.5:
            risk.append((fa.id, fp))
    health_rows.sort(key=lambda r: str(r["i"]))  # same lock order as other writers: no deadlocks with the background sync
    for i in range(0, len(health_rows), 300):
        await db.execute(text("update fixed_assets set failure_probability=:f, health_score=:h where id=:i"), health_rows[i:i + 300])
    counts["assets_health_set"] = len(health_rows)

    # ---- maintenance baselines of the diesel locomotives (feeds the living maintenance plan); about 12% are overdue
    intervals = (await db.execute(text("select id, code, interval_km from maintenance_intervals where code in ('ТО-1','ТО-2','ТО-3','ТР-1','ТР-2','ТР-3') and interval_km is not null"))).all()
    n_base = 0
    overdue: list[tuple[Any, str, float]] = []
    for a in [x for x in assets if x.asset_type == "diesel"]:
        mileage = float(a.mileage or 0)
        for iv in intervals:
            late = rng.random() < 0.12
            frac = rng.uniform(1.0, 1.3) if late else rng.uniform(0.08, 0.95)
            km = max(0.0, mileage - frac * float(iv.interval_km))
            done = today - timedelta(days=int(min(700, max(3, frac * float(iv.interval_km) / 120))))
            await db.execute(text(
                "insert into asset_maintenance_baseline (asset_id, interval_id, done_at, km, source, note) values (:a,:i,:d,:k,:s,:n) on conflict do nothing"),
                {"a": a.id, "i": iv.id, "d": done, "k": round(km, 2), "s": rng.choice(["import", "import", "manual"]), "n": MARK})
            n_base += 1
            if late:
                overdue.append((a, iv.code, (frac - 1) * float(iv.interval_km)))
    counts["maintenance_baselines"] = n_base

    # ---- disruptions: the fixed set plus ones spread over the whole period
    some_assets = [a for a in loco_assets if a.asset_type == "diesel"][:8] or loco_assets[:8]
    extra = []
    kinds_pool = [("parts", "section", "Нет материалов на складе, ждём поставку"), ("no_bay", "section", "Канава занята, постановка в ремонт перенесена"),
                  ("no_crew", "section", "Нехватка слесарей: отпуска и больничные"), ("unit_unavailable", "asset", "Тепловоз занят на маневровой работе, в ремонт не поставлен"),
                  ("accident", "asset", "Происшествие на путях, техника простаивает до комиссии"), ("weather", "all", "Непогода, наружные работы остановлены"),
                  ("sensor_failure", "section", "Сбой датчиков пробега, данные уточняются"), ("unplanned_repair", "asset", "Внеплановый ремонт сорвал плановое ТО"),
                  ("other", "all", "Плановое отключение электроэнергии")]
    for _ in range(22):
        k, sc, note = rng.choice(kinds_pool)
        began = rng.randint(35, 230)
        length = rng.randint(1, 9)
        extra.append((k, sc, rng.choice(["ЖДЦ-1", "ЖДЦ-2"]) if sc == "section" else None, began, max(began - length, 0) if rng.random() < 0.92 else None, note))
    n_dis = 0
    for kind, scope, sec, started_ago, ended_ago, note in DISRUPTIONS + extra:
        asset = rng.choice(some_assets) if scope == "asset" else None
        ends = (today - timedelta(days=ended_ago)) if ended_ago is not None else None
        await db.execute(text(
            "insert into maintenance_disruption (kind, scope, asset_id, section_id, starts_on, ends_on, status, note, closed_at) values (:k,:sc,:a,:s,:st,:e,:stat,:n,:c)"),
            {"k": kind, "sc": scope, "a": asset.id if asset else None, "s": sections[sec] if sec else None, "st": today - timedelta(days=started_ago), "e": ends,
             "stat": "closed" if ends else "open", "n": f"{note} {MARK}", "c": now - timedelta(days=ended_ago) if ended_ago is not None else None})
        n_dis += 1
    counts["maintenance_disruption"] = n_dis

    # ---- readiness trend (dashboard chart): the last DAYS days rise from about 81% to about 93% with short dips after accidents
    dips: dict[Any, float] = {}
    for p in problems:
        if p["scenario"] == "accident" and p["info"]["closed_at"]:
            d0 = p["info"]["closed_at"].astimezone(timezone.utc).date()
            for k in range(0, 4):
                dips[d0 + timedelta(days=k)] = dips.get(d0 + timedelta(days=k), 0) + 0.018
    by_sec: dict[Any, int] = {}
    for a in assets:
        by_sec[a.section_id] = by_sec.get(a.section_id, 0) + 1
    scope_counts = {"all": len(assets), **{str(k): v for k, v in by_sec.items()}}
    sec_of = {str(k): k for k in by_sec}
    await db.execute(text("delete from daily_readiness_snapshots where snapshot_date >= :d"), {"d": today - timedelta(days=DAYS + 5)})
    n_snap = 0
    for scope, total in scope_counts.items():
        for d in range(DAYS, 0, -1):
            day = today - timedelta(days=d)
            base = 0.81 + 0.125 * (DAYS - d) / DAYS
            level = min(0.975, max(0.7, base + rng.uniform(-0.012, 0.012) - dips.get(day, 0)))
            ready = min(total, max(0, round(total * level)))
            await db.execute(text(
                "insert into daily_readiness_snapshots (snapshot_date, scope_key, section_id, asset_count, ready_count, availability_percent) "
                "values (:d,:k,:s,:t,:r,:p) on conflict do nothing"),
                {"d": day, "k": scope, "s": sec_of.get(scope), "t": total, "r": ready, "p": round(100.0 * ready / total, 2) if total else 0})
            n_snap += 1
    counts["daily_readiness_snapshots"] = n_snap

    # ---- AI insights: what the system "found" (problems), forecasts (risk assets, overdue ТО) and a few positive notes
    async def add_insight(asset_id: Any, order_id: Any, itype: str, sev: str, prob: float, msg: str, action: str, created: datetime, resolved: bool, details: dict[str, Any]) -> None:
        await db.execute(text(
            "insert into ai_insights (asset_id, work_order_id, insight_type, probability, severity, message, suggested_action, details, is_resolved, created_at) "
            "values (:a,:o,:t,:p,:sv,:m,:sa,CAST(:d AS jsonb),:r,:c)"),
            {"a": asset_id, "o": order_id, "t": itype, "p": round(min(0.9999, max(0.0, prob)), 4), "sv": sev, "m": f"{msg} {MARK}", "sa": action,
             "d": json.dumps({"demo": True, **details}, ensure_ascii=False), "r": resolved, "c": min(created, now)})

    n_ins = 0
    for p in problems:
        inf = p["info"]
        created = (inf["closed_at"] or inf["created"]) + timedelta(hours=1)
        old = (now - created).days > 14
        await add_insight(inf["asset"].id, inf["id"], p["type"], p["severity"], rng.uniform(0.72, 0.97), p["message"], p["action"], created, old and rng.random() < 0.8,
                          {"scenario": p["scenario"], "work_order": inf["number"], "executor": inf["executor"], **p["details"]})
        n_ins += 1
    ids_loco = {a.id: a for a in loco_assets}
    for aid, fp in sorted(risk, key=lambda x: -x[1])[:30]:
        a = ids_loco.get(aid) or next((w for w in wagon_assets if w.id == aid), None)
        if not a:
            continue
        days = rng.randint(6, 40)
        await add_insight(aid, None, "prediction", "critical" if fp >= 0.8 else "high", fp, f"{a.inv_number}: вероятность отказа {round(fp * 100)}% в ближайшие {days} дн., прогноз по истории ремонтов и пробегу",
                          "Поставить в плановый осмотр до наступления срока", now - timedelta(days=rng.randint(0, 20), hours=rng.randint(0, 20)), False,
                          {"remaining_days": days, "predicted_failure_km": round(float(a.mileage or 0) + days * 150)})
        n_ins += 1
    for a, icode, over in overdue[:14]:
        await add_insight(a.id, None, "prediction", "high" if over > 3000 else "medium", rng.uniform(0.55, 0.85), f"{a.inv_number}: просрочено {icode} на {round(over)} км. Плановое ТО не выполнено вовремя",
                          f"Запланировать {icode} в ближайшую смену", now - timedelta(days=rng.randint(0, 15)), False, {"interval": icode, "overdue_km": round(over)})
        n_ins += 1
    for a in rng.sample(pool_loco, k=min(10, len(pool_loco))):
        await add_insight(a.id, None, "efficiency", "low", rng.uniform(0.6, 0.9), f"{a.inv_number}: расход ТМЦ на {rng.randint(8, 18)}% ниже нормы за последние 3 ремонта, лучший результат по участку",
                          "Закрепить практику исполнителя как образец", now - timedelta(days=rng.randint(1, 25)), rng.random() < 0.3, {"positive": True})
        n_ins += 1
    counts["ai_insights"] = n_ins

    counts.update(await _seed_parts_analytics(db, rng, today, wt, nom, loco_assets, wagon_assets, wh))

    await db.commit()
    return counts


SUPPLIERS = ["ООО «ТехСнаб»", "АО «Темирйулмашсервис»", "ООО «Метиз-Сервис»", "ООО «РельсКомплект»", "ИП Каримов (Ташкент)", "ООО «АвтоЗапчасть Плюс»"]
IMPORT_SUPPLIERS = ["Rail Parts GmbH (Германия)", "TransMash Ltd (Россия)", "CRRC Spare (Китай)"]
DEMO_WAGON_INTERVALS = [("ТО-2В", 180), ("ДР", 1095), ("КРВ", 2190)]
LOCO_PLAN_SPREAD = {"ТО-1": (5, 60, 1.0), "ТО-2": (10, 120, 0.8), "ТО-3": (20, 200, 0.6), "ТР-1": (30, 300, 0.4), "ТР-2": (60, 330, 0.25), "ТР-3": (100, 360, 0.12), "СР": (150, 360, 0.05), "КР": (200, 360, 0.03)}


async def _seed_parts_analytics(db: AsyncSession, rng: random.Random, today: Any, wt: dict, nom: dict, loco_assets: list, wagon_assets: list, wh: list[str]) -> dict[str, int]:
    """Plan rows for the next year, stock balances, supplier terms and purchase orders so every spare-part analytics card has content."""
    out: dict[str, int] = {}
    intervals = {r.code: r.id for r in (await db.execute(text("select id, code from maintenance_intervals where is_active"))).all()}
    for code, days in DEMO_WAGON_INTERVALS:  # the real intervals are locomotive-only; the demo adds wagon repair intervals (the name carries the demo marker)
        if code in intervals or code not in wt:
            continue
        intervals[code] = await _one(db, "insert into maintenance_intervals (work_type_id, code, name, interval_days, asset_types, rank) values (:w,:c,:n,:d,'{wagon,tank_car,platform}',:r) returning id",
                                     w=wt[code][0], c=code, n=f"{code} {MARK}", d=days, r={"ТО-2В": 1, "ДР": 2, "КРВ": 3}[code])
        out["intervals"] = out.get("intervals", 0) + 1

    async def plan(asset: Any, code: str, days: int) -> int:
        if code not in intervals:
            return 0
        done = await db.execute(text(
            "insert into maintenance_plan (asset_id, interval_id, status, trigger_mileage, scheduled_date, blocked_note) values (:a,:i,'scheduled',:t,:d,:m) on conflict do nothing"),
            {"a": asset.id, "i": intervals[code], "t": round(float(asset.mileage or 0) + days * 150), "d": today + timedelta(days=days), "m": MARK})
        return done.rowcount or 0

    n_plan = 0
    for a in loco_assets[:70]:
        for code, (lo, hi, share) in LOCO_PLAN_SPREAD.items():
            if rng.random() < share:
                n_plan += await plan(a, code, rng.randint(lo, hi))
    for a in wagon_assets[:140]:
        for code, lo, hi, share in (("ТО-2В", 5, 175, 1.0), ("ДР", 30, 360, 0.25), ("КРВ", 120, 360, 0.04)):
            if rng.random() < share:
                n_plan += await plan(a, code, rng.randint(lo, hi))
    out["maintenance_plan"] = n_plan

    hist = {r.nomenclature_id: float(r.q) for r in (await db.execute(text(
        "select i.nomenclature_id, sum(i.qty) q from tmc_document_items i join tmc_documents d on d.id=i.document_id "
        "where d.status in ('issued','closed') and d.doc_date >= :f and i.nomenclature_id is not null group by 1"), {"f": today - timedelta(days=180)})).all()}
    from app.services import parts_analytics  # the demand the risk engine will see (plan x norms) calibrates the stock levels

    planned, _gaps, _price = await parts_analytics._planned_demand(db, None, today, True)
    catalog = [(dept, it) for dept, items in nom.items() for it in items]
    n_stock = n_terms = n_orders = 0
    risky: list[tuple[Any, float, int]] = []  # (item, daily demand, lead time): about to run out before the delivery
    low: list[tuple[Any, float, int]] = []
    fine: list[tuple[Any, float, int]] = []
    for dept, it in catalog:
        roll = rng.random()
        has_demand = hist.get(it["id"], 0.0) > 0 or planned.get(it["id"], {}).get("quarter", {}).get("qty", 0.0) > 0
        if not has_demand and rng.random() < 0.85:
            continue  # a part nobody consumes needs no stock row in the demo
        daily = max(hist.get(it["id"], 0.0) / 180.0, planned.get(it["id"], {}).get("quarter", {}).get("qty", 0.0) / 90.0, 0.03)
        lead = rng.choice([14, 21, 30, 30, 45, 60, 90]) if rng.random() < 0.9 else 120
        terms = not (roll >= 0.6 and rng.random() < 0.15)  # a few parts keep the lead time unknown on purpose (the card shows the default and a flag)
        if roll < 0.60:
            days_cover = rng.uniform(lead + 60, lead + 330)
        elif roll < 0.80:
            days_cover = rng.uniform(lead + 1, lead + 18)
        elif roll < 0.92:
            days_cover = rng.uniform(4, max(6, lead * 0.7))
        else:
            days_cover = None  # no 1C balance at all
        if terms:
            await db.execute(text(
                "insert into supplier_terms (nomenclature_id, supplier, lead_time_days, min_order_qty, safety_days, note) values (:n,:s,:l,:m,:sf,:nt) on conflict do nothing"),
                {"n": it["id"], "s": rng.choice(IMPORT_SUPPLIERS if lead >= 90 else SUPPLIERS), "l": lead, "m": None if it["unit"] in ("кг", "л", "м") else rng.choice([None, 2, 4, 10]),
                 "sf": rng.choice([7, 14, 14, 21]), "nt": MARK})
            n_terms += 1
        if days_cover is None:
            continue
        total = daily * days_cover
        integral = it["unit"] in ("шт", "шт.", "компл")
        parts = [1.0] if rng.random() < 0.6 else [0.6, 0.4]
        for k, share in enumerate(parts):
            qty = total * share
            qty = float(max(0, int(qty))) if integral else round(qty, 1)
            await db.execute(text(
                "insert into stock_balances (nomenclature_id, warehouse, qty, unit, as_of, source) values (:n,:w,:q,:u,:d,'demo') on conflict do nothing"),
                {"n": it["id"], "w": wh[(k + len(it["name"])) % len(wh)], "q": qty, "u": it["unit"], "d": today - timedelta(days=rng.randint(0, 3))})
            n_stock += 1
        if 0.80 <= roll < 0.92:
            risky.append((it, daily, lead))
        elif 0.60 <= roll < 0.80:
            low.append((it, daily, lead))
        else:
            fine.append((it, daily, lead))
    out["stock_balances"], out["supplier_terms"] = n_stock, n_terms

    async def order(it: Any, qty: float, status: str, ordered: int, expected: int | None, received: float = 0.0) -> None:
        integral = it["unit"] in ("шт", "шт.", "компл")
        q = float(max(1, round(qty))) if integral else round(max(qty, 1.0), 1)
        await db.execute(text(
            "insert into purchase_orders (nomenclature_id, doc_no, supplier, qty, qty_received, ordered_on, expected_on, status, note) values (:n,:d,:s,:q,:r,:o,:e,:st,:nt)"),
            {"n": it["id"], "d": f"ПО-Д-{n_orders + 1:04d}", "s": rng.choice(SUPPLIERS), "q": q, "r": min(received, q), "o": today - timedelta(days=ordered),
             "e": today + timedelta(days=expected) if expected is not None else None, "st": status, "nt": MARK})

    rng.shuffle(risky)
    rng.shuffle(low)
    for i, (it, daily, lead) in enumerate(risky[:10]):  # will run out before the delivery: the order is late (or there is none)
        if i % 3 == 2:
            continue
        await order(it, daily * 120, "in_transit" if i % 2 else "ordered", rng.randint(3, 20), lead + rng.randint(5, 40))
        n_orders += 1
    for i, (it, daily, lead) in enumerate(low[:12]):  # an order on the way in time
        if i % 2 == 1:
            continue
        status = ("ordered", "in_transit", "partial")[i % 3 % 2 + (1 if i % 5 == 0 else 0)]
        await order(it, daily * 150, status, rng.randint(5, 25), rng.randint(3, max(4, lead // 2)), received=daily * 40 if status == "partial" else 0.0)
        n_orders += 1
    for i, (it, daily, lead) in enumerate(fine[:7]):  # routine replenishment of parts that are fine
        await order(it, daily * 120, ("ordered", "in_transit")[i % 2], rng.randint(2, 12), rng.randint(20, lead + 20))
        n_orders += 1
    for i, (it, daily, lead) in enumerate((low + risky)[12:16]):  # history: received and cancelled orders (must not count)
        await order(it, daily * 90, "received" if i % 2 == 0 else "cancelled", rng.randint(60, 120), None, received=daily * 90 if i % 2 == 0 else 0.0)
        n_orders += 1
    out["purchase_orders"] = n_orders
    return out


async def reset(db: AsyncSession) -> dict[str, int]:
    """Removes everything an earlier demo-seed wrote (rows are recognised by their demo markers). Only in `toir_demo`."""
    if settings.postgres_db != "toir_demo":
        raise ValueError(f"Refused: the demo reset works only in the database 'toir_demo' (this one is '{settings.postgres_db}')")
    removed: dict[str, int] = {}

    async def run(name: str, sql: str) -> None:
        removed[name] = (await db.execute(text(sql))).rowcount or 0

    await run("purchase_orders", "delete from purchase_orders where note like '[ДЕМО]%'")
    await run("supplier_terms", "delete from supplier_terms where note like '[ДЕМО]%'")
    await run("stock_balances", "delete from stock_balances where source = 'demo'")
    await run("maintenance_plan", "delete from maintenance_plan where blocked_note like '[ДЕМО]%'")
    await run("maintenance_intervals", "delete from maintenance_intervals mi where mi.name like '% [ДЕМО]' and not exists (select 1 from maintenance_plan mp where mp.interval_id = mi.id)")
    await run("assets_restored", "update fixed_assets set status='operational' where status in ('maintenance','repair') and id in "
              "(select fixed_asset_id from work_orders where note like '[ДЕМО]%' and status='in_progress')")
    await run("maintenance_log", "delete from maintenance_log m using tmc_document_items i, tmc_documents d, work_orders wo, fixed_assets fa, work_types wt "
              "where i.document_id=d.id and d.doc_no like 'Д-%' and wo.id=d.work_order_id and fa.id=wo.fixed_asset_id and wt.id=d.work_type_id "
              "and m.item_name=i.name and m.qty=i.qty and m.equipment=fa.inv_number and m.work_type=wt.code and m.maintenance_date=d.doc_date")
    await run("tmc_documents", "delete from tmc_documents where doc_no like 'Д-%'")
    await run("ai_insights", "delete from ai_insights where message like '%[ДЕМО]%'")
    await run("work_orders", "delete from work_orders where note like '[ДЕМО]%'")
    await run("maintenance_disruption", "delete from maintenance_disruption where note like '%[ДЕМО]%'")
    await run("asset_maintenance_baseline", "delete from asset_maintenance_baseline where note like '[ДЕМО]%'")
    await run("work_type_templates", "delete from work_type_templates where note like '[ДЕМО]%'")
    await run("nomenclature", "delete from nomenclature where code like 'ДЕМО-%'")
    await run("employees", "delete from employees where tab_number like 'Д-%'")
    await db.commit()
    return removed
