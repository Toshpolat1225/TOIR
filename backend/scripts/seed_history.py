"""Generate two years of marked history data through the authenticated HTTP API.

Every generated row carries a GT-HIST / GT- marker so it can be filtered or
removed later. The script is resumable: completed asset numbers are stored in a
local state file and existing work orders are detected by description.

The API cannot backdate closed_at or mileage_history.recorded_at, therefore the
dates are corrected afterwards with backend/scripts/sql/fix_history_dates.sql.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import random
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, time as dt_time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from e2e_smoke import ApiResponse, ApiSession, SmokeError, parse_object

BASE_URL = os.environ.get("TOIR_API_BASE_URL", "http://localhost:8010").rstrip("/")
MARKER = "GT-HIST"
HISTORY_DAYS = 730
MILEAGE_BLOCKS = 24
ORDER_TIMEOUT = 60
TOKEN_LIFETIME_SECONDS = 20 * 60

SMALL_DETAILS = {
    "wagon": [
        "осмотр тележек и колёсных пар",
        "проверка тормозной системы",
        "ревизия автосцепки",
        "замена тормозных колодок",
        "проверка бортов и дверей",
        "смазка узлов ходовой части",
        "диагностика пневматики",
        "осмотр кузова и крыши",
    ],
    "locomotive": [
        "обслуживание дизеля",
        "диагностика тягового двигателя",
        "проверка токоприёмника",
        "ревизия вспомогательных машин",
        "замена масляного фильтра",
        "регулировка форсунок",
        "проверка цепей управления",
        "осмотр экипажной части",
        "обслуживание компрессора",
    ],
}

MAJOR_DETAILS = {
    "wagon": [
        "средний ремонт тележки",
        "капитальный ремонт кузова",
        "замена колёсной пары",
        "ремонт автосцепного устройства",
        "капитальный ремонт тормозной системы",
    ],
    "locomotive": [
        "средний ремонт дизеля",
        "капитальный ремонт тягового двигателя",
        "замена турбокомпрессора",
        "ремонт экипажной части",
        "капитальный ремонт электрической схемы",
    ],
}

NOTE_POOL = [
    "Выполнено по заявке мастера участка.",
    "Обнаружен повышенный износ, заменена деталь.",
    "Работы согласованы с диспетчером депо.",
    "После ремонта проведена проверка под нагрузкой.",
    "Требуется повторный осмотр через 30 дней.",
    "Замечаний после выполнения работ нет.",
    None,
    None,
    None,
]

SMALL_PRIORITIES = ["low", "normal", "normal", "normal", "high", "high", "critical"]
MAJOR_PRIORITIES = ["normal", "high", "high", "critical"]

WAGON_SERIES = ["11-217", "12-132", "12-196", "13-401", "13-9744", "ЦМГВ", "11-066", "12-726"]
ELECTRIC_SERIES = ["ВЛ80С", "ВЛ80Т", "ВЛ10У", "ВЛ65", "2ЭС6", "O'ZBEKISTON-1"]
DIESEL_SERIES = ["ТЭМ18ДМ", "2ТЭ10М", "ЧМЭ3", "ТЭ33А", "ТЭП70БС"]

SURNAMES = [
    "Абдуллаев", "Ахмедов", "Каримов", "Рахимов", "Юсупов", "Мирзаев",
    "Ибрагимов", "Саидов", "Турсунов", "Шарипов", "Норматов", "Хасанов",
    "Махмудов", "Эргашев", "Собиров", "Джалилов", "Кучкаров", "Ташкенбаев",
    "Бекмуратов", "Азизов",
]
FIRST_NAMES = [
    "Азамат", "Алишер", "Бахтиёр", "Дилшод", "Жасур", "Ильхам", "Камол",
    "Лутфулла", "Мансур", "Нодир", "Отабек", "Рустам", "Санжар", "Тимур",
    "Улугбек", "Фарход", "Шерзод", "Элёр", "Юлдаш", "Яхё",
]
PATRONYMICS = [
    "Абдуллаевич", "Ахмедович", "Бахтиёрович", "Дилшодович", "Жасурович",
    "Ильхамович", "Камолович", "Мансурович", "Нодирович", "Рустамович",
    "Санжарович", "Тимурович", "Улугбекович", "Фарходович", "Шерзодович",
]
POSITIONS = ["Мастер участка", "Слесарь-ремонтник", "Электромонтёр", "Бригадир", "Механик"]

MATERIALS: list[tuple[str, str, int]] = [
    ("Подшипник роликовый 30-42726", "шт.", 185_000),
    ("Колодка тормозная 256-011", "шт.", 96_000),
    ("Масло трансмиссионное ТМ-5", "л", 42_000),
    ("Смазка Литол-24", "кг", 68_000),
    ("Фильтр масляный", "шт.", 145_000),
    ("Фильтр воздушный", "шт.", 210_000),
    ("Прокладка ГБЦ", "шт.", 125_000),
    ("Ремень приводной", "шт.", 87_000),
    ("Щётка электродвигателя", "шт.", 156_000),
    ("Контакт медный", "шт.", 74_000),
    ("Изолятор фарфоровый", "шт.", 320_000),
    ("Кран машиниста", "компл.", 1_250_000),
    ("Рукав тормозной", "шт.", 98_000),
    ("Болт М20х100", "шт.", 12_000),
    ("Гайка М20", "шт.", 6_500),
    ("Шайба пружинная", "шт.", 3_200),
    ("Эмаль ПФ-115", "кг", 54_000),
    ("Растворитель Р-646", "л", 28_000),
    ("Провод монтажный ПВ3", "м", 15_500),
    ("Предохранитель 10А", "шт.", 4_500),
    ("Поршень компрессора", "шт.", 680_000),
    ("Клапан впускной", "шт.", 245_000),
    ("Форсунка дизеля", "шт.", 890_000),
    ("Турбокомпрессор", "шт.", 4_200_000),
    ("Гидравлическое масло", "л", 62_000),
    ("Антифриз", "л", 38_000),
    ("Тормозная жидкость", "л", 41_000),
    ("Колёсная пара", "компл.", 5_200_000),
    ("Букса", "шт.", 720_000),
    ("Рессора", "шт.", 450_000),
    ("Автосцепка", "шт.", 980_000),
    ("Поглощающий аппарат", "шт.", 1_350_000),
    ("Дверь вагона", "шт.", 620_000),
    ("Окно вагона", "шт.", 180_000),
    ("Огнетушитель", "шт.", 210_000),
    ("Аптечка", "компл.", 95_000),
    ("Светильник", "шт.", 76_000),
    ("Датчик скорости", "шт.", 340_000),
    ("Манометр", "шт.", 128_000),
    ("Термометр", "шт.", 64_000),
    ("Кабель силовой", "м", 72_000),
    ("Резистор", "шт.", 112_000),
    ("Контактор", "шт.", 540_000),
    ("Реле", "шт.", 330_000),
    ("Аккумулятор", "шт.", 1_850_000),
    ("Стеклоочиститель", "шт.", 88_000),
    ("Песок", "т", 120_000),
    ("Метизы крепёжные", "компл.", 45_000),
]


def api_request(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    bearer: str | None = None,
    session: ApiSession | None = None,
    timeout: int = ORDER_TIMEOUT,
) -> ApiResponse:
    headers: dict[str, str] = {}
    body: bytes | None = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if bearer is not None:
        headers["Authorization"] = f"Bearer {bearer}"
    http_request = Request(
        f"{BASE_URL}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        opener = session.opener if session is not None else build_opener()
        with opener.open(http_request, timeout=timeout) as response:
            return ApiResponse(
                response.status,
                {name.lower(): value for name, value in response.headers.items()},
                response.read(),
            )
    except HTTPError as response:
        body = response.read()
        response.close()
        return ApiResponse(
            response.code,
            {name.lower(): value for name, value in response.headers.items()},
            body,
        )
    except (URLError, TimeoutError, OSError) as exc:
        raise SmokeError("API request failed; verify that the tunnel is available") from exc


def response_detail(response: ApiResponse) -> str:
    text = response.body[:300].decode("utf-8", "replace")
    return f"HTTP {response.status} {text}".strip()


class WorkerClient:
    """One authenticated session per worker thread with automatic refresh."""

    def __init__(self, email: str, password: str) -> None:
        self.email = email
        self.password = password
        self.session = ApiSession()
        self.token: str | None = None
        self.issued_at = 0.0
        self.login()

    def login(self) -> None:
        response = api_request(
            "POST",
            "/api/v1/auth/login",
            payload={"email": self.email, "password": self.password},
            session=self.session,
        )
        if response.status != 200:
            raise SmokeError(f"Admin login failed: {response_detail(response)}")
        token = parse_object(response).get("access_token")
        if not isinstance(token, str) or not token:
            raise SmokeError("Login response did not include an access token")
        self.token = token
        self.issued_at = time.monotonic()

    def refresh(self) -> None:
        response = api_request("POST", "/api/v1/auth/refresh", session=self.session)
        if response.status != 200:
            self.login()
            return
        token = parse_object(response).get("access_token")
        if not isinstance(token, str) or not token:
            self.login()
            return
        self.token = token
        self.issued_at = time.monotonic()

    def ensure_token(self) -> None:
        if time.monotonic() - self.issued_at >= TOKEN_LIFETIME_SECONDS:
            self.refresh()

    def call(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> ApiResponse:
        self.ensure_token()
        response = api_request(
            method, path, payload=payload, bearer=self.token, session=self.session
        )
        if response.status == 401:
            self.refresh()
            response = api_request(
                method, path, payload=payload, bearer=self.token, session=self.session
            )
        return response


def list_all(client: WorkerClient, endpoint: str, **params: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    offset = 0
    while True:
        query = dict(params)
        query["limit"] = 1000
        query["offset"] = offset
        response = client.call("GET", f"{endpoint}?{urlencode(query)}")
        if response.status != 200:
            raise SmokeError(f"Could not read {endpoint}: {response_detail(response)}")
        data = parse_object(response)
        page = data.get("items")
        if not isinstance(page, list):
            raise SmokeError(f"Unexpected list response from {endpoint}")
        items.extend(row for row in page if isinstance(row, dict))
        total = int(data.get("total", len(items)))
        offset += len(page)
        if not page or offset >= total:
            return items


def create_entity(
    client: WorkerClient, endpoint: str, payload: dict[str, Any], label: str
) -> dict[str, Any]:
    response = client.call("POST", endpoint, payload)
    if response.status not in {200, 201}:
        raise SmokeError(f"{label} failed: {response_detail(response)}")
    return parse_object(response)


def _is_small_type(work_type: dict[str, Any]) -> bool:
    text = f"{work_type.get('code', '')} {work_type.get('name', '')}".upper()
    return "ТО" in text and "ТР" not in text


def _is_major_type(work_type: dict[str, Any]) -> bool:
    text = f"{work_type.get('code', '')} {work_type.get('name', '')}".upper()
    return "ТР" in text or "КР" in text


def ensure_work_types(
    client: WorkerClient, existing: list[dict[str, Any]]
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    result: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for unit_type, label in (("locomotive", "локомотив"), ("wagon", "вагон")):
        pool = [row for row in existing if row.get("unit_type") == unit_type]
        small = [row for row in pool if _is_small_type(row)]
        major = [row for row in pool if _is_major_type(row)]
        created: list[dict[str, Any]] = []
        if not small:
            created.append(
                create_entity(
                    client,
                    "/api/v1/work-types",
                    {
                        "code": f"GT-HIST-TO-{label[0].upper()}",
                        "name": f"ТО-1 (тестовая история, {label})",
                        "unit_type": unit_type,
                        "sort_order": 900,
                    },
                    f"Create work type TO ({unit_type})",
                )
            )
            small = [created[-1]]
        if not major:
            created.append(
                create_entity(
                    client,
                    "/api/v1/work-types",
                    {
                        "code": f"GT-HIST-TR-{label[0].upper()}",
                        "name": f"ТР-2 (тестовая история, {label})",
                        "unit_type": unit_type,
                        "sort_order": 901,
                    },
                    f"Create work type TR ({unit_type})",
                )
            )
            major = [created[-1]]
        result[unit_type] = {"small": small, "major": major}
    return result


def _employee_name(rng: random.Random) -> str:
    return (
        f"{rng.choice(SURNAMES)} {rng.choice(FIRST_NAMES)} "
        f"{rng.choice(PATRONYMICS)}"
    )


def ensure_departments_and_sections(
    client: WorkerClient,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    departments = list_all(client, "/api/v1/departments")
    sections = list_all(client, "/api/v1/sections")
    if not departments:
        colors = ["#3b82f6", "#10b981", "#f59e0b"]
        for index in range(3):
            departments.append(
                create_entity(
                    client,
                    "/api/v1/departments",
                    {
                        "name": f"GT-HIST департамент {index + 1}",
                        "color": colors[index % len(colors)],
                    },
                    f"Create department {index + 1}",
                )
            )
    if not sections:
        for index in range(6):
            sections.append(
                create_entity(
                    client,
                    "/api/v1/sections",
                    {
                        "name": f"GT-HIST участок {index + 1}",
                        "department_id": departments[index % len(departments)]["id"],
                    },
                    f"Create section {index + 1}",
                )
            )
    return departments, sections


@dataclass(frozen=True)
class AssetSpec:
    index: int
    inv_number: str
    name: str
    asset_type: str
    series: str
    section_index: int
    year_built: int
    comm_date: date
    initial_mileage: Decimal
    monthly_km: Decimal
    initial_cost: Decimal
    status: str


def read_status_codes(client: WorkerClient) -> dict[str, str]:
    defaults = {
        "operational": "operational",
        "maintenance": "maintenance",
        "repair": "repair",
        "out_of_service": "out_of_service",
    }
    try:
        rows = list_all(
            client, "/api/v1/fixed-asset-catalogs/statuses", is_active="true"
        )
    except SmokeError:
        return defaults
    by_behavior = {
        str(row.get("behavior")): str(row.get("code"))
        for row in rows
        if row.get("behavior") and row.get("code")
    }
    fallback = str(rows[0]["code"]) if rows else None
    if fallback is None:
        return defaults
    return {
        behavior: by_behavior.get(behavior, fallback)
        for behavior in defaults
    }


def build_asset_specs(
    sections: list[dict[str, Any]],
    wagons: int,
    electric: int,
    diesel: int,
    seed: int,
    status_codes: dict[str, str],
) -> list[AssetSpec]:
    rng = random.Random(seed)
    today = date.today()
    specs: list[AssetSpec] = []

    def add(
        count: int,
        prefix: str,
        asset_type: str,
        series_pool: list[str],
        mileage_low: int,
        mileage_high: int,
        monthly_low: int,
        monthly_high: int,
        cost_low: int,
        cost_high: int,
        name_template: str,
    ) -> None:
        for number in range(1, count + 1):
            index = len(specs)
            series = rng.choice(series_pool)
            year_built = rng.randint(1986, 2022)
            comm_date = date(year_built, 1, 1) + timedelta(days=rng.randint(0, 900))
            comm_date = min(comm_date, today - timedelta(days=1000))
            specs.append(
                AssetSpec(
                    index=index,
                    inv_number=f"{prefix}-{number:04d}",
                    name=name_template.format(
                        series=series,
                        number=10000 + number + (index % 7) * 137,
                    ),
                    asset_type=asset_type,
                    series=series,
                    section_index=index % len(sections),
                    year_built=year_built,
                    comm_date=comm_date,
                    initial_mileage=_dec(rng.randint(mileage_low, mileage_high)),
                    monthly_km=_dec(rng.randint(monthly_low, monthly_high)),
                    initial_cost=_dec(rng.randint(cost_low, cost_high), "1"),
                    status=status_codes[
                        rng.choices(
                            ["operational", "maintenance", "repair", "out_of_service"],
                            weights=[85, 8, 5, 2],
                        )[0]
                    ],
                )
            )

    add(
        wagons, "GT-W", "wagon", WAGON_SERIES,
        20_000, 180_000, 900, 3_600, 80_000_000, 450_000_000,
        "Полувагон {series} № {number}",
    )
    add(
        electric, "GT-L", "locomotive", ELECTRIC_SERIES,
        200_000, 1_400_000, 7_000, 16_000, 1_200_000_000, 3_500_000_000,
        "Электровоз {series}-{number}",
    )
    add(
        diesel, "GT-D", "diesel", DIESEL_SERIES,
        150_000, 900_000, 4_000, 11_000, 700_000_000, 2_200_000_000,
        "Тепловоз {series}-{number}",
    )
    return specs


def ensure_employees(
    client: WorkerClient,
    sections: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    used_section_ids: set[str],
) -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(712)
    by_section: dict[str, list[dict[str, Any]]] = {}
    for row in existing:
        if row.get("is_active", True):
            by_section.setdefault(str(row.get("section_id")), []).append(row)
    per_section = max(1, min(4, 120 // max(1, len(used_section_ids))))
    existing_numbers = {str(row.get("tab_number")) for row in existing}
    counter = 1

    for section in sections:
        section_id = str(section["id"])
        if section_id not in used_section_ids:
            continue
        pool = by_section.setdefault(section_id, [])
        while len(pool) < per_section:
            while f"GT-E-{counter:04d}" in existing_numbers:
                counter += 1
            tab_number = f"GT-E-{counter:04d}"
            counter += 1
            row = create_entity(
                client,
                "/api/v1/employees",
                {
                    "tab_number": tab_number,
                    "full_name": _employee_name(rng),
                    "position": rng.choice(POSITIONS),
                    "section_id": section_id,
                },
                f"Create employee {tab_number}",
            )
            existing_numbers.add(tab_number)
            pool.append(row)
    return by_section


@dataclass
class References:
    departments: list[dict[str, Any]]
    sections: list[dict[str, Any]]
    work_types: dict[str, dict[str, list[dict[str, Any]]]]
    employees_by_section: dict[str, list[dict[str, Any]]]
    nomenclature: list[dict[str, Any]]
    norms: dict[tuple[str, str, str], Decimal]
    fallback_department_id: str | None
    sections_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)


def ensure_nomenclature(
    client: WorkerClient,
    departments: list[dict[str, Any]],
    work_types: dict[str, dict[str, list[dict[str, Any]]]],
) -> tuple[list[dict[str, Any]], dict[tuple[str, str, str], Decimal]]:
    existing = list_all(client, "/api/v1/nomenclature")
    by_code = {str(row.get("code")): row for row in existing}
    rng = random.Random(913)
    materials: list[dict[str, Any]] = []
    for index, (name, unit, _price) in enumerate(MATERIALS, 1):
        code = f"GT-M-{index:03d}"
        row = by_code.get(code)
        if row is None:
            row = create_entity(
                client,
                "/api/v1/nomenclature",
                {
                    "department_id": departments[(index - 1) % len(departments)]["id"],
                    "name": name,
                    "code": code,
                    "unit": unit,
                    "extra": {"label": "GT-HIST", "generated": True},
                },
                f"Create nomenclature {code}",
            )
        materials.append(row)

    all_types = [
        work_type
        for unit_types in work_types.values()
        for group in ("small", "major")
        for work_type in unit_types[group]
    ]
    unique_types = {str(row["id"]): row for row in all_types}
    existing_norms = list_all(client, "/api/v1/nomenclature-norms")
    norms: dict[tuple[str, str, str], Decimal] = {}
    for row in existing_norms:
        try:
            key = (
                str(row["nomenclature_id"]),
                str(row["department_id"]),
                str(row["work_type_id"]),
            )
            norms[key] = Decimal(str(row["standard_quantity"]))
        except (KeyError, TypeError, ValueError):
            continue

    for index, material in enumerate(materials):
        department_id = str(material["department_id"])
        base_price = MATERIALS[index][2]
        for work_type_id, work_type in unique_types.items():
            key = (str(material["id"]), department_id, work_type_id)
            if key in norms:
                continue
            standard = Decimal(str(round(rng.uniform(0.5, 8.0), 3)))
            if standard <= 0:
                standard = Decimal("1")
            price = _dec(base_price * rng.uniform(0.95, 1.15))
            try:
                create_entity(
                    client,
                    "/api/v1/nomenclature-norms",
                    {
                        "nomenclature_id": material["id"],
                        "department_id": department_id,
                        "work_type_id": work_type["id"],
                        "standard_quantity": f"{standard:.3f}",
                        "avg_price": f"{price:.2f}",
                        "min_quantity": f"{standard * Decimal('0.5'):.3f}",
                        "max_quantity": f"{standard * Decimal('2'):.3f}",
                    },
                    f"Create norm {material.get('code')} / {work_type.get('code')}",
                )
            except SmokeError:
                continue
            norms[key] = standard
    return materials, norms


def ensure_intervals(
    client: WorkerClient,
    work_types: dict[str, dict[str, list[dict[str, Any]]]],
) -> None:
    existing = list_all(client, "/api/v1/maintenance-intervals")
    covered = {
        asset_type
        for row in existing
        for asset_type in row.get("asset_types", [])
    }
    specs = [
        ("wagon", "GT-HIST-INT-TO-W", "ТО вагонов (тестовая история)", 12_000, 30, ["wagon"]),
        ("wagon", "GT-HIST-INT-TR-W", "ТР вагонов (тестовая история)", 120_000, 730, ["wagon"]),
        ("locomotive", "GT-HIST-INT-TO-L", "ТО локомотивов (тестовая история)", 15_000, 30, ["locomotive", "diesel"]),
        ("locomotive", "GT-HIST-INT-TR-L", "ТР локомотивов (тестовая история)", 300_000, 730, ["locomotive", "diesel"]),
    ]
    for unit_key, code, name, interval_km, interval_days, asset_types in specs:
        if all(asset_type in covered for asset_type in asset_types):
            continue
        group = "small" if "-TO-" in code else "major"
        work_type = work_types[unit_key][group][0]
        try:
            create_entity(
                client,
                "/api/v1/maintenance-intervals",
                {
                    "work_type_id": work_type["id"],
                    "code": code,
                    "name": name,
                    "interval_km": str(interval_km),
                    "interval_days": interval_days,
                    "asset_types": asset_types,
                    "warn_percent": "10",
                    "is_active": True,
                },
                f"Create interval {code}",
            )
        except SmokeError:
            continue

@dataclass
class PlannedOrder:
    index: int
    start: datetime
    end: datetime
    status: str
    order_kind: str
    priority: str
    description: str
    note: str | None
    executor_id: str
    chief_id: str | None
    repairs: list[dict[str, Any]]


@dataclass
class _Event:
    start: datetime
    kind: str


def _dec(value: float | int | str, places: str = "0.01") -> Decimal:
    return Decimal(str(value)).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _at(day: date, hour: int, minute: int) -> datetime:
    return datetime.combine(day, dt_time(hour, minute), tzinfo=timezone.utc)


def _norm_for(
    refs: References, nomenclature_id: str, department_id: str | None, work_type_id: str
) -> Decimal:
    if department_id is not None:
        value = refs.norms.get((nomenclature_id, department_id, work_type_id))
        if value is not None:
            return value
    candidates = [
        value
        for (nom_id, _dept_id, wt_id), value in refs.norms.items()
        if nom_id == nomenclature_id and wt_id == work_type_id
    ]
    return candidates[0] if candidates else Decimal("1")


def _repair_payload(
    work_type: dict[str, Any],
    material_pool: list[dict[str, Any]],
    refs: References,
    department_id: str | None,
    rng: random.Random,
) -> dict[str, Any]:
    count = rng.randint(1, min(4, len(material_pool)))
    chosen = rng.sample(material_pool, count)
    items: list[dict[str, Any]] = []
    for material in chosen:
        standard = _norm_for(
            refs, str(material["id"]), department_id, str(work_type["id"])
        )
        if rng.random() < 0.08:
            factor = rng.uniform(1.25, 2.2)
        else:
            factor = rng.uniform(0.6, 1.15)
        qty = max(Decimal("0.1"), standard * Decimal(str(round(factor, 4))))
        items.append(
            {
                "nomenclature_id": material["id"],
                "name": material["name"],
                "inv_no": None,
                "unit": material["unit"],
                "qty": f"{qty:.3f}",
                "note": rng.choice(NOTE_POOL) if rng.random() < 0.15 else None,
            }
        )
    return {"work_type_id": work_type["id"], "items": items}


def build_plans(
    spec: AssetSpec,
    refs: References,
    employees: list[dict[str, Any]],
    department_id: str | None,
    seed: int,
    small_count: int,
    major_min: int,
    major_max: int,
    now: datetime,
) -> list[PlannedOrder]:
    content_rng = random.Random(seed * 1_000_003 + spec.index)
    date_rng = random.Random(seed * 7_000_019 + spec.index)
    status_rng = random.Random(seed * 13_000_033 + spec.index)
    today = now.date()
    start_day = today - timedelta(days=HISTORY_DAYS - 1)
    span = HISTORY_DAYS - 12
    events: list[_Event] = []

    for index in range(small_count):
        if index == small_count - 1:
            day = today - timedelta(days=date_rng.randint(4, 18))
        else:
            offset = (
                (index + date_rng.uniform(0.15, 0.85))
                * span
                / max(1, small_count - 1)
            )
            day = start_day + timedelta(days=offset)
        events.append(
            _Event(
                _at(day, date_rng.randint(8, 17), date_rng.randint(0, 59)),
                "small",
            )
        )

    major_count = date_rng.randint(major_min, major_max)
    for major in range(major_count):
        fraction = (major + 1) / (major_count + 1)
        offset = fraction * span + date_rng.uniform(-10, 10)
        offset = max(0, min(span, offset))
        day = start_day + timedelta(days=offset)
        events.append(
            _Event(
                _at(day, date_rng.randint(8, 15), date_rng.randint(0, 59)),
                "major",
            )
        )

    events.sort(key=lambda event: event.start)
    small_indices = [i for i, event in enumerate(events) if event.kind == "small"]
    recent_cut = now - timedelta(days=25)
    old_cut = now - timedelta(days=45)
    recent_small = [i for i in small_indices if events[i].start >= recent_cut]
    old_small = [i for i in small_indices if events[i].start < old_cut]

    statuses = {i: "completed" for i in range(len(events))}
    in_progress_index = status_rng.choice(recent_small)
    statuses[in_progress_index] = "in_progress"
    pending_recent_pool = [i for i in recent_small if i != in_progress_index]
    recent_pending_index = (
        status_rng.choice(pending_recent_pool) if pending_recent_pool else None
    )
    if recent_pending_index is not None:
        statuses[recent_pending_index] = "pending"

    overdue_index = status_rng.choice(old_small) if old_small else None
    if overdue_index is not None:
        statuses[overdue_index] = "pending"
    cancelled_pool = [i for i in old_small if i != overdue_index]
    for cancelled_index in status_rng.sample(
        cancelled_pool, min(2, len(cancelled_pool))
    ):
        statuses[cancelled_index] = "cancelled"

    unit_key = "wagon" if spec.asset_type == "wagon" else "locomotive"
    section_employees = employees or [
        row for rows in refs.employees_by_section.values() for row in rows
    ]
    material_pool = [
        row for row in refs.nomenclature
        if department_id is None or str(row.get("department_id")) == str(department_id)
    ] or refs.nomenclature

    plans: list[PlannedOrder] = []
    for order_index, event in enumerate(events):
        kind = event.kind
        pool = refs.work_types[unit_key]["small" if kind == "small" else "major"]
        work_type = content_rng.choice(pool)
        repairs = [
            _repair_payload(
                work_type, material_pool, refs, department_id, content_rng
            )
        ]
        if len(pool) > 1 and content_rng.random() < 0.08:
            second = content_rng.choice(
                [row for row in pool if row["id"] != work_type["id"]]
            )
            repairs.append(
                _repair_payload(
                    second, material_pool, refs, department_id, content_rng
                )
            )

        status = statuses[order_index]
        if status == "completed":
            duration = (
                timedelta(hours=date_rng.randint(2, 20))
                if kind == "small"
                else timedelta(days=date_rng.randint(2, 10))
            )
            end = event.start + duration
            if end > now - timedelta(hours=1):
                end = now - timedelta(hours=date_rng.randint(1, 12))
            if end <= event.start:
                end = event.start + timedelta(minutes=30)
        elif status == "cancelled":
            end = min(
                event.start + timedelta(hours=date_rng.randint(1, 8)), now
            )
        elif status == "in_progress":
            end = now + timedelta(days=date_rng.randint(2, 10))
        else:
            if event.start < now - timedelta(days=10):
                end = event.start + timedelta(days=date_rng.randint(1, 4))
            else:
                end = now + timedelta(days=date_rng.randint(3, 14))

        detail_pool = (
            SMALL_DETAILS[unit_key] if kind == "small" else MAJOR_DETAILS[unit_key]
        )
        detail = content_rng.choice(detail_pool)
        description = (
            f"{MARKER}-{spec.inv_number}-{order_index + 1:03d}: "
            f"{work_type.get('name', 'Работа')} — {detail}"
        )
        if kind == "small":
            order_kind = content_rng.choices(
                ["planned", "unplanned", "repair", "emergency"],
                weights=[60, 25, 10, 5],
            )[0]
            priority = content_rng.choice(SMALL_PRIORITIES)
        else:
            order_kind = content_rng.choices(
                ["planned", "unplanned", "repair", "emergency"],
                weights=[20, 10, 60, 10],
            )[0]
            priority = content_rng.choice(MAJOR_PRIORITIES)

        executor = content_rng.choice(section_employees)
        chief = (
            content_rng.choice(section_employees)
            if content_rng.random() < 0.3 and len(section_employees) > 1
            else None
        )
        plans.append(
            PlannedOrder(
                index=order_index,
                start=event.start,
                end=end,
                status=status,
                order_kind=order_kind,
                priority=priority,
                description=description,
                note=content_rng.choice(NOTE_POOL),
                executor_id=str(executor["id"]),
                chief_id=str(chief["id"]) if chief else None,
                repairs=repairs,
            )
        )
    return plans


def block_mileage(spec: AssetSpec, block: int) -> Decimal:
    return (spec.initial_mileage + spec.monthly_km * block).quantize(Decimal("0.01"))


def existing_orders(client: WorkerClient, asset_id: str) -> dict[str, dict[str, Any]]:
    rows = list_all(
        client,
        "/api/v1/work-orders",
        fixed_asset_id=asset_id,
        q=MARKER,
    )
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        description = row.get("description")
        if isinstance(description, str) and description.startswith(MARKER):
            result[description] = row
    return result


def find_order(
    client: WorkerClient, asset_id: str, marker: str
) -> dict[str, Any] | None:
    response = client.call(
        "GET",
        "/api/v1/work-orders?"
        + urlencode({"fixed_asset_id": asset_id, "q": marker, "limit": 1000}),
    )
    if response.status != 200:
        return None
    data = parse_object(response)
    for row in data.get("items", []):
        if str(row.get("description", "")).startswith(marker):
            return row
    return None


def get_order(client: WorkerClient, order_id: str) -> dict[str, Any] | None:
    response = client.call("GET", f"/api/v1/work-orders/{order_id}")
    if response.status != 200:
        return None
    return parse_object(response)


def patch_status(client: WorkerClient, order_id: str, target: str) -> None:
    last_error = ""
    for attempt in range(3):
        try:
            response = client.call(
                "PATCH", f"/api/v1/work-orders/{order_id}", {"status": target}
            )
        except SmokeError as exc:
            last_error = str(exc)
            time.sleep(1 + attempt)
            continue
        if response.status == 200:
            return
        if response.status == 409:
            current = get_order(client, order_id)
            if current is not None and current.get("status") == target:
                return
            raise SmokeError(
                f"Status {target} rejected for order {order_id}: "
                f"{response_detail(response)}"
            )
        if response.status in {500, 502, 503, 504}:
            last_error = response_detail(response)
            time.sleep(1 + attempt)
            continue
        raise SmokeError(
            f"Status {target} failed for order {order_id}: {response_detail(response)}"
        )
    current = get_order(client, order_id)
    if current is not None and current.get("status") == target:
        return
    raise SmokeError(f"Status {target} failed for order {order_id}: {last_error}")


def ensure_order_status(client: WorkerClient, row: dict[str, Any], target: str) -> None:
    current = row.get("status")
    order_id = str(row["id"])
    if current == target:
        return
    if target == "completed":
        if current == "pending":
            patch_status(client, order_id, "in_progress")
            current = "in_progress"
        if current == "in_progress":
            patch_status(client, order_id, "completed")
        return
    if target == "in_progress" and current == "pending":
        patch_status(client, order_id, "in_progress")
        return
    if target == "cancelled" and current in {"pending", "in_progress"}:
        patch_status(client, order_id, "cancelled")


def create_order(
    client: WorkerClient, payload: dict[str, Any], marker: str
) -> dict[str, Any]:
    last_error = ""
    for attempt in range(4):
        response: ApiResponse | None = None
        try:
            response = client.call("POST", "/api/v1/work-orders", payload)
        except SmokeError as exc:
            last_error = str(exc)
        if response is not None:
            if response.status == 201:
                return parse_object(response)
            if response.status == 409:
                last_error = response_detail(response)
                time.sleep(0.5 + attempt * 0.5)
            elif response.status in {500, 502, 503, 504}:
                last_error = response_detail(response)
                time.sleep(1 + attempt)
            else:
                raise SmokeError(
                    f"Create order failed for {marker}: {response_detail(response)}"
                )
        found = find_order(client, str(payload["fixed_asset_id"]), marker)
        if found is not None:
            return found
        time.sleep(1 + attempt)
    raise SmokeError(f"Create order failed for {marker}: {last_error}")


def process_asset(
    client: WorkerClient,
    spec: AssetSpec,
    asset: dict[str, Any],
    refs: References,
    was_created_now: bool,
    small_count: int,
    major_min: int,
    major_max: int,
    seed: int,
) -> tuple[int, list[str]]:
    now = datetime.now(timezone.utc)
    today = now.date()
    history_start = today - timedelta(days=HISTORY_DAYS - 1)
    section = refs.sections_by_id.get(str(asset.get("section_id")))
    if section is None:
        section = refs.sections[spec.section_index % len(refs.sections)]
    section_id = str(asset.get("section_id") or section["id"])
    department_id = section.get("department_id") or refs.fallback_department_id
    plans = build_plans(
        spec,
        refs,
        refs.employees_by_section.get(section_id, []),
        department_id,
        seed,
        small_count,
        major_min,
        major_max,
        now,
    )
    known = {} if was_created_now else existing_orders(client, str(asset["id"]))
    current_mileage = Decimal(str(asset.get("mileage") or "0"))

    errors: list[str] = []
    created = 0
    next_block = 0
    for plan in plans:
        target_block = min(
            MILEAGE_BLOCKS - 1,
            max(0, (plan.start.date() - history_start).days // 30),
        )
        while next_block <= target_block:
            value = block_mileage(spec, next_block)
            if value > current_mileage:
                try:
                    response = client.call(
                        "POST",
                        f"/api/v1/fixed-assets/{asset['id']}/mileage",
                        {"mileage": f"{value:.2f}"},
                    )
                except SmokeError as exc:
                    errors.append(f"{spec.inv_number} mileage: {exc}")
                    response = None
                if response is not None and response.status == 200:
                    current_mileage = value
                elif response is not None:
                    errors.append(
                        f"{spec.inv_number} mileage: {response_detail(response)}"
                    )
            next_block += 1

        row = known.get(plan.description)
        marker = plan.description.split(":", 1)[0]
        if row is None:
            payload = {
                "fixed_asset_id": str(asset["id"]),
                "section_id": section_id,
                "department_id": department_id,
                "order_kind": plan.order_kind,
                "priority": plan.priority,
                "executor_id": plan.executor_id,
                "chief_id": plan.chief_id,
                "description": plan.description,
                "note": plan.note,
                "date_start": plan.start.isoformat(),
                "date_end": plan.end.isoformat(),
                "repairs": plan.repairs,
            }
            try:
                row = create_order(client, payload, marker)
                created += 1
                known[plan.description] = row
            except SmokeError as exc:
                errors.append(f"{marker}: {exc}")
                continue
        try:
            ensure_order_status(client, row, plan.status)
        except SmokeError as exc:
            errors.append(f"{marker} status {plan.status}: {exc}")

    final_mileage = block_mileage(spec, MILEAGE_BLOCKS - 1)
    if final_mileage > current_mileage:
        try:
            response = client.call(
                "POST",
                f"/api/v1/fixed-assets/{asset['id']}/mileage",
                {"mileage": f"{final_mileage:.2f}"},
            )
            if response.status != 200:
                errors.append(
                    f"{spec.inv_number} final mileage: {response_detail(response)}"
                )
        except SmokeError as exc:
            errors.append(f"{spec.inv_number} final mileage: {exc}")
    return created, errors


class ProgressState:
    def __init__(self, path: Path, base_url: str) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.data: dict[str, Any] = {
            "base_url": base_url,
            "completed": [],
            "errors": {},
            "orders": 0,
        }
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(loaded, dict) and loaded.get("base_url") == self.data["base_url"]:
            self.data["completed"] = list(loaded.get("completed", []))
            self.data["errors"] = dict(loaded.get("errors", {}))
            self.data["orders"] = int(loaded.get("orders", 0))

    def save(self) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(self.path)

    def completed(self) -> set[str]:
        with self.lock:
            return set(self.data["completed"])

    def mark_completed(self, inv_number: str, orders: int) -> None:
        with self.lock:
            if inv_number not in self.data["completed"]:
                self.data["completed"].append(inv_number)
            self.data["orders"] = int(self.data.get("orders", 0)) + orders
            self.data["errors"].pop(inv_number, None)
            self.save()

    def record_error(self, inv_number: str, message: str) -> None:
        with self.lock:
            values = self.data["errors"].setdefault(inv_number, [])
            if message not in values:
                values.append(message)
            del values[5:]
            self.save()


def ensure_assets(
    client: WorkerClient,
    specs: list[AssetSpec],
    sections: list[dict[str, Any]],
    seed: int,
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    existing = list_all(client, "/api/v1/fixed-assets", q="GT-")
    by_inv = {
        str(row.get("inv_number")): row
        for row in existing
        if str(row.get("inv_number", "")).startswith("GT-")
    }
    rng = random.Random(seed + 1)
    created_now: set[str] = set()
    for index, spec in enumerate(specs, 1):
        if spec.inv_number in by_inv:
            continue
        section = sections[spec.section_index % len(sections)]
        today = date.today()
        payload = {
            "inv_number": spec.inv_number,
            "name": spec.name,
            "asset_type": spec.asset_type,
            "series": spec.series,
            "depot": section.get("name"),
            "section_id": section["id"],
            "status": spec.status,
            "comm_date": spec.comm_date.isoformat(),
            "year_built": spec.year_built,
            "mileage": f"{spec.initial_mileage:.2f}",
            "last_maint_date": (today - timedelta(days=rng.randint(5, 90))).isoformat(),
            "next_maint_date": (today + timedelta(days=rng.randint(1, 60))).isoformat(),
            "initial_cost": f"{spec.initial_cost:.2f}",
            "owner": "АО «Узбекистон темир йуллари»",
        }
        row = create_entity(
            client, "/api/v1/fixed-assets", payload, f"Create asset {spec.inv_number}"
        )
        by_inv[spec.inv_number] = row
        created_now.add(spec.inv_number)
        if index % 100 == 0:
            print(f"  assets created: {index}/{len(specs)}", flush=True)
    return by_inv, created_now


def main() -> int:
    global BASE_URL
    parser = argparse.ArgumentParser(
        description="Generate two years of marked GT-HIST data through the API"
    )
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--wagons", type=int, default=1000)
    parser.add_argument("--electric", type=int, default=100)
    parser.add_argument("--diesel", type=int, default=50)
    parser.add_argument("--small-repairs", type=int, default=100)
    parser.add_argument("--major-min", type=int, default=2)
    parser.add_argument("--major-max", type=int, default=3)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument(
        "--state-file",
        default=str(Path(tempfile.gettempdir()) / "toir_seed_history_state.json"),
    )
    args = parser.parse_args()

    if args.wagons < 0 or args.electric < 0 or args.diesel < 0:
        print("Asset counts must not be negative.")
        return 2
    if args.wagons + args.electric + args.diesel == 0:
        print("At least one asset is required.")
        return 2
    if args.small_repairs < 1 or args.major_min < 0 or args.major_max < args.major_min:
        print("Check repair counts: small >= 1, 0 <= major-min <= major-max.")
        return 2

    BASE_URL = args.base_url.rstrip("/")
    health = api_request("GET", "/health", timeout=20)
    if health.status != 200:
        print(f"API health check failed: {response_detail(health)}")
        return 2

    email = getpass.getpass("Admin email: ").strip()
    password = getpass.getpass("Admin password: ")
    if not email or not password:
        print("Admin email and password are required.")
        return 2

    state = ProgressState(Path(args.state_file), BASE_URL)
    print(f"API: {BASE_URL}")
    print(f"State file: {args.state_file}")
    print(
        f"Scale: {args.wagons} wagons, {args.electric} electric, "
        f"{args.diesel} diesel; {args.small_repairs} small + "
        f"{args.major_min}-{args.major_max} major repairs per asset"
    )

    try:
        setup = WorkerClient(email, password)
        departments, sections = ensure_departments_and_sections(setup)
        status_codes = read_status_codes(setup)
        specs = build_asset_specs(
            sections,
            args.wagons,
            args.electric,
            args.diesel,
            args.seed,
            status_codes,
        )
        work_types = ensure_work_types(
            setup, list_all(setup, "/api/v1/work-types")
        )
        used_sections = {str(sections[i]["id"]) for i in {s.section_index for s in specs}}
        employees_existing = list_all(
            setup, "/api/v1/employees", is_active="true"
        )
        employees_by_section = ensure_employees(
            setup, sections, employees_existing, used_sections
        )
        nomenclature, norms = ensure_nomenclature(setup, departments, work_types)
        ensure_intervals(setup, work_types)
        sections_by_id = {str(row["id"]): row for row in sections}
        fallback_department_id = (
            str(departments[0]["id"]) if departments else None
        )
        refs = References(
            departments=departments,
            sections=sections,
            work_types=work_types,
            employees_by_section=employees_by_section,
            nomenclature=nomenclature,
            norms=norms,
            fallback_department_id=fallback_department_id,
            sections_by_id=sections_by_id,
        )
        print(
            f"References ready: {len(sections)} sections, "
            f"{len(nomenclature)} materials, {len(norms)} norms, "
            f"{sum(len(v) for v in employees_by_section.values())} employees"
        )
        assets, created_now = ensure_assets(setup, specs, sections, args.seed)
        print(f"Assets ready: {len(assets)}")
    except SmokeError as exc:
        print(f"Setup stopped: {exc}")
        return 1

    completed = state.completed()
    pending = [spec for spec in specs if spec.inv_number not in completed]
    missing = [spec.inv_number for spec in pending if spec.inv_number not in assets]
    if missing:
        print(f"Missing assets after setup: {missing[:5]}")
        return 1
    print(f"Assets already completed: {len(specs) - len(pending)}")
    print(f"Assets to process: {len(pending)}")

    local = threading.local()
    progress_lock = threading.Lock()
    started_at = time.monotonic()
    counters = {"done": 0, "orders": 0, "failed": 0}

    def worker(spec: AssetSpec) -> tuple[str, int, list[str]]:
        client = getattr(local, "client", None)
        if client is None:
            client = WorkerClient(email, password)
            local.client = client
        created, errors = process_asset(
            client,
            spec,
            assets[spec.inv_number],
            refs,
            spec.inv_number in created_now,
            args.small_repairs,
            args.major_min,
            args.major_max,
            args.seed,
        )
        if errors:
            state.record_error(spec.inv_number, errors[0])
        else:
            state.mark_completed(spec.inv_number, created)
        return spec.inv_number, created, errors

    failed_assets: list[AssetSpec] = []
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(worker, spec): spec for spec in pending}
            for future in as_completed(futures):
                spec = futures[future]
                try:
                    inv_number, created, errors = future.result()
                except Exception as exc:  # noqa: BLE001 - keep the run alive
                    state.record_error(spec.inv_number, str(exc))
                    inv_number, created, errors = spec.inv_number, 0, [str(exc)]
                with progress_lock:
                    counters["done"] += 1
                    counters["orders"] += created
                    if errors:
                        counters["failed"] += 1
                        failed_assets.append(spec)
                    done = counters["done"]
                    elapsed = max(0.01, time.monotonic() - started_at)
                    if done % 5 == 0 or done == len(pending):
                        print(
                            f"[{done}/{len(pending)}] assets | "
                            f"{counters['orders']} orders | "
                            f"{counters['failed']} failed | "
                            f"{counters['orders'] / elapsed:.1f} orders/s",
                            flush=True,
                        )
    except KeyboardInterrupt:
        print("\nStopped by user. Progress is saved; rerun the same command to resume.")
        return 130

    if failed_assets:
        state_errors = state.data.get("errors", {})
        print(f"Failed assets: {len(failed_assets)}")
        for spec in failed_assets[:20]:
            messages = state_errors.get(spec.inv_number, [])
            print(f"  {spec.inv_number}: {messages[-1] if messages else 'unknown error'}")
        print("Rerun the same command to retry failed assets.")
        return 1

    print("All requested assets processed.")
    print("Next step: run backend/scripts/sql/fix_history_dates.sql on the server.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
