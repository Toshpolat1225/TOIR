"""Create or remove clearly marked demo rows through the authenticated HTTP API."""

from __future__ import annotations

import argparse
import getpass
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from e2e_refs import _record_created
from e2e_smoke import (
    ApiSession,
    Check,
    SmokeError,
    check_condition,
    check_status,
    parse_object,
    print_results,
    request,
    require_status,
)
from e2e_workorders import _record_id


def _list_all(token: str, endpoint: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = request(
            "GET",
            f"{endpoint}?{urlencode({'limit': 1000, 'offset': offset})}",
            bearer=token,
        )
        if response.status != 200:
            raise SmokeError(f"Could not read {endpoint}: HTTP {response.status}")
        data = parse_object(response)
        page = data.get("items")
        if not isinstance(page, list):
            raise SmokeError(f"Unexpected list response from {endpoint}")
        items.extend(row for row in page if isinstance(row, dict))
        total = int(data.get("total", len(items)))
        offset += len(page)
        if not page or offset >= total:
            return items


def _create(
    checks: list[Check],
    created: list[tuple[str, str]],
    token: str,
    endpoint: str,
    payload: dict[str, Any],
    label: str,
) -> dict[str, Any]:
    response = request("POST", endpoint, bearer=token, payload=payload)
    record_id = _record_created(checks, created, label, response, endpoint)
    row = parse_object(response)
    row["id"] = record_id
    return row


def _remove_rows(
    checks: list[Check], token: str, endpoint: str, rows: list[dict[str, Any]],
    predicate,
) -> None:
    for row in rows:
        if not predicate(row):
            continue
        record_id = row.get("id")
        if not record_id:
            continue
        response = request("DELETE", f"{endpoint}/{record_id}", bearer=token)
        check_condition(
            checks,
            f"Remove {endpoint.rsplit('/', 1)[-1]} DEMO row",
            response.status in {204, 404},
            f"HTTP {response.status}",
        )


def _is_demo(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("DEMO-")


def _authenticate(checks: list[Check], email: str, password: str) -> str:
    response = request(
        "POST",
        "/api/v1/auth/login",
        payload={"email": email, "password": password},
        session=ApiSession(),
    )
    require_status(checks, "Admin login", response, 200)
    token = parse_object(response).get("access_token")
    if not isinstance(token, str) or not token:
        raise SmokeError("Admin login response did not include an access token")
    return token


def _remove_demo(checks: list[Check], token: str) -> None:
    orders = _list_all(token, "/api/v1/work-orders")
    norms = _list_all(token, "/api/v1/nomenclature-norms")
    intervals = _list_all(token, "/api/v1/maintenance-intervals")
    assets = _list_all(token, "/api/v1/fixed-assets")
    employees = _list_all(token, "/api/v1/employees")
    nomenclature = _list_all(token, "/api/v1/nomenclature")
    demo_nomenclature_ids = {
        row.get("id") for row in nomenclature if _is_demo(row.get("code"))
    }

    # Delete dependents first so API foreign-key checks remain satisfied.
    _remove_rows(checks, token, "/api/v1/work-orders", orders,
                 lambda row: _is_demo(row.get("description")))
    _remove_rows(checks, token, "/api/v1/maintenance-intervals", intervals,
                 lambda row: _is_demo(row.get("code")))
    _remove_rows(checks, token, "/api/v1/nomenclature-norms", norms,
                 lambda row: row.get("nomenclature_id") in demo_nomenclature_ids)
    _remove_rows(checks, token, "/api/v1/nomenclature", nomenclature,
                 lambda row: _is_demo(row.get("code")))
    _remove_rows(checks, token, "/api/v1/fixed-assets", assets,
                 lambda row: _is_demo(row.get("inv_number")))
    _remove_rows(checks, token, "/api/v1/employees", employees,
                 lambda row: _is_demo(row.get("tab_number")))


def _seed_demo(checks: list[Check], token: str) -> None:
    sections = _list_all(token, "/api/v1/sections")
    departments = _list_all(token, "/api/v1/departments")
    work_types = _list_all(token, "/api/v1/work-types")
    if not sections:
        raise SmokeError("Create at least one section before seeding demo data")
    if not departments:
        raise SmokeError("Create at least one department before seeding demo data")
    if not work_types:
        raise SmokeError("Create at least one work type before seeding demo data")

    employees = _list_all(token, "/api/v1/employees")
    assets = _list_all(token, "/api/v1/fixed-assets")
    nomenclature = _list_all(token, "/api/v1/nomenclature")
    norms = _list_all(token, "/api/v1/nomenclature-norms")
    intervals = _list_all(token, "/api/v1/maintenance-intervals")
    orders = _list_all(token, "/api/v1/work-orders")
    created: list[tuple[str, str]] = []

    employees_by_number = {row.get("tab_number"): row for row in employees}
    demo_employees: list[dict[str, Any]] = []
    for index in range(1, 7):
        number = f"DEMO-{index:03d}"
        employee = employees_by_number.get(number)
        if employee is None:
            section = sections[(index - 1) % len(sections)]
            employee = _create(
                checks, created, token, "/api/v1/employees",
                {
                    "tab_number": number,
                    "full_name": f"Demo Employee {index:03d}",
                    "position": "NAMUNA xodim",
                    "section_id": section["id"],
                },
                f"Create employee {number}",
            )
        demo_employees.append(employee)

    assets_by_number = {row.get("inv_number"): row for row in assets}
    asset_specs = [
        ("ПЭ-2У 111", "locomotive", "operational", "ПЭ-2У", 128450),
        ("ТЭМ18Д 204", "diesel", "maintenance", "ТЭМ18Д", 88420),
        ("2ТЭ10М 315", "diesel", "repair", "2ТЭ10М", 219760),
        ("ЧМЭ3 407", "locomotive", "operational", "ЧМЭ3", 176300),
        ("Вагон 501", "wagon", "operational", "ЦМГВ", 56320),
        ("Вагон 502", "wagon", "maintenance", "ЦМГВ", 74810),
        ("Вагон 503", "wagon", "repair", "ЦМГВ", 91240),
        ("Вагон 504", "wagon", "operational", "ЦМГВ", 33700),
    ]
    demo_assets: list[dict[str, Any]] = []
    for index, (name, asset_type, asset_status, series, mileage) in enumerate(asset_specs, 1):
        inv_number = f"DEMO-{index:03d}"
        asset = assets_by_number.get(inv_number)
        if asset is None:
            section = sections[(index - 1) % len(sections)]
            asset = _create(
                checks, created, token, "/api/v1/fixed-assets",
                {
                    "inv_number": inv_number,
                    "name": name,
                    "asset_type": asset_type,
                    "series": series,
                    "depot": section.get("name") or "NAMUNA depo",
                    "section_id": section["id"],
                    "status": asset_status,
                    "mileage": str(mileage),
                },
                f"Create asset {inv_number}",
            )
        demo_assets.append(asset)

    departments_by_id = {row.get("id"): row for row in departments}
    sections_by_id = {row.get("id"): row for row in sections}
    nomenclature_by_code = {row.get("code"): row for row in nomenclature}
    demo_nomenclature: list[dict[str, Any]] = []
    units = ["шт.", "л", "кг", "м", "компл."]
    for index in range(1, 11):
        code = f"DEMO-{index:03d}"
        item = nomenclature_by_code.get(code)
        if item is None:
            section = sections[(index - 1) % len(sections)]
            department_id = section.get("department_id")
            if department_id not in departments_by_id:
                department_id = departments[(index - 1) % len(departments)]["id"]
            item = _create(
                checks, created, token, "/api/v1/nomenclature",
                {
                    "department_id": department_id,
                    "name": f"NAMUNA material {index:02d}",
                    "code": code,
                    "unit": units[(index - 1) % len(units)],
                    "extra": {"label": "NAMUNA", "is_demo": True},
                },
                f"Create nomenclature {code}",
            )
        demo_nomenclature.append(item)

    work_types_by_unit = {
        unit: [row for row in work_types if row.get("unit_type") == unit]
        for unit in ("locomotive", "wagon")
    }
    existing_norms = {
        (str(row.get("nomenclature_id")), str(row.get("work_type_id"))): row
        for row in norms
    }
    standard_by_pair: dict[tuple[str, str], Decimal] = {}
    demo_norms: list[dict[str, Any]] = []
    for index, item in enumerate(demo_nomenclature):
        section = sections[(index) % len(sections)]
        department_id = item.get("department_id") or section.get("department_id")
        choices = work_types_by_unit.get("locomotive", []) + work_types_by_unit.get("wagon", [])
        work_type = choices[index % len(choices)] if choices else work_types[index % len(work_types)]
        key = (str(item["id"]), str(work_type["id"]))
        norm = existing_norms.get(key)
        if norm is None:
            norm = _create(
                checks, created, token, "/api/v1/nomenclature-norms",
                {
                    "nomenclature_id": item["id"],
                    "department_id": department_id,
                    "work_type_id": work_type["id"],
                    "standard_quantity": "10",
                    "avg_price": str(12500 + index * 1750),
                },
                f"Create norm for DEMO-{index + 1:03d}",
            )
        demo_norms.append(norm)
        standard_by_pair[key] = Decimal(str(norm.get("standard_quantity", 10)))

    demo_intervals_by_code = {row.get("code"): row for row in intervals}
    interval_specs = [
        ("DEMO-INTERVAL-TO1", "NAMUNA — ТО-1", 10000, 30),
        ("DEMO-INTERVAL-TO2", "NAMUNA — ТО-2", 30000, 90),
        ("DEMO-INTERVAL-TR1", "NAMUNA — ТР-1", 60000, 180),
    ]
    for index, (code, name, interval_km, interval_days) in enumerate(interval_specs):
        if code in demo_intervals_by_code:
            continue
        unit_types = sorted({asset.get("asset_type") for asset in demo_assets})
        _create(
            checks, created, token, "/api/v1/maintenance-intervals",
            {
                "work_type_id": work_types[index % len(work_types)]["id"],
                "code": code,
                "name": name,
                "interval_km": interval_km,
                "interval_days": interval_days,
                "asset_types": unit_types,
                "warn_percent": "10",
                "is_active": True,
            },
            f"Create interval {code}",
        )

    orders_by_description = {row.get("description"): row for row in orders}
    now = datetime.now(timezone.utc).replace(microsecond=0)
    order_specs = [
        ("pending", None),
        ("in_progress", None),
        ("completed", None),
        ("overdue", now.replace(year=2000)),
        ("pending", None),
        ("completed", None),
    ]
    demo_work_types = [row.get("work_type_id") for row in demo_norms]
    nomenclature_ids = [row["id"] for row in demo_nomenclature]
    for index, (target_status, old_date) in enumerate(order_specs, 1):
        description = f"DEMO-WO-{index:02d} NAMUNA buyurtma"
        if description in orders_by_description:
            continue
        asset = demo_assets[(index - 1) % len(demo_assets)]
        employee = next(
            (row for row in demo_employees if row.get("section_id") == asset.get("section_id")),
            demo_employees[0],
        )
        section = sections_by_id.get(asset.get("section_id"), sections[0])
        nomenclature_id = nomenclature_ids[(index - 1) % len(nomenclature_ids)]
        work_type_id = demo_work_types[(index - 1) % len(demo_work_types)]
        pair = (str(nomenclature_id), str(work_type_id))
        standard = standard_by_pair.get(pair, Decimal("10"))
        quantity = standard * Decimal("1.3") if index == 1 else standard
        if index == 1:
            check_condition(
                checks,
                "First order item exceeds its norm by more than 20%",
                standard > 0 and quantity > standard * Decimal("1.2"),
                f"Quantity {quantity}; standard {standard}",
            )
        start_date = old_date or now
        payload = {
            "fixed_asset_id": asset["id"],
            "section_id": asset["section_id"],
            "department_id": section.get("department_id"),
            "order_kind": "repair" if index % 2 else "planned",
            "priority": "high" if index == 4 else "normal",
            "executor_id": employee["id"],
            "description": description,
            "date_start": start_date.isoformat(),
            "date_end": old_date.isoformat() if old_date else None,
            "repairs": [{
                "work_type_id": work_type_id,
                "items": [{
                    "nomenclature_id": nomenclature_id,
                    "name": f"NAMUNA item {index:02d}",
                    "inv_no": f"DEMO-ITEM-{index:02d}",
                    "unit": "шт.",
                    "qty": str(quantity),
                    "note": "NAMUNA; test data",
                }],
            }],
        }
        order_response = request(
            "POST", "/api/v1/work-orders", bearer=token, payload=payload
        )
        _record_created(
            checks, created, f"Create work order {index}/6", order_response,
            "/api/v1/work-orders",
        )
        order_id = _record_id(order_response)
        if target_status == "overdue":
            check_condition(
                checks,
                "Overdue order is recognized by the API",
                parse_object(order_response).get("is_overdue") is True,
                "API marks the past-due open order overdue"
                if parse_object(order_response).get("is_overdue") is True
                else "API did not mark the past-due open order overdue",
            )
        status = "pending"
        if target_status in {"in_progress", "completed"}:
            response = request(
                "PATCH", f"/api/v1/work-orders/{order_id}", bearer=token,
                payload={"status": "in_progress"},
            )
            check_status(checks, f"Set order {index} in progress", response, 200)
            status = "in_progress"
        if target_status == "completed":
            response = request(
                "PATCH", f"/api/v1/work-orders/{order_id}", bearer=token,
                payload={"status": "completed"},
            )
            check_status(checks, f"Complete order {index}", response, 200)
            status = "completed"
        check_condition(
            checks,
            f"Order {index} status is {target_status}",
            status == ("pending" if target_status == "overdue" else target_status),
            f"Stored status: {status}",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed or remove DEMO sample records using the API")
    parser.add_argument("--remove", action="store_true", help="remove only rows with DEMO identifiers")
    args = parser.parse_args()
    checks: list[Check] = []
    email = getpass.getpass("Admin email: ").strip()
    password = getpass.getpass("Admin password: ")
    if not email or not password:
        print("Admin email and password are required.")
        return 2
    stopped_reason: str | None = None
    try:
        token = _authenticate(checks, email, password)
        if args.remove:
            _remove_demo(checks, token)
        else:
            _seed_demo(checks, token)
    except SmokeError as exc:
        stopped_reason = str(exc)
        print(f"Demo seed stopped: {exc}")
    print_results(checks)
    return 1 if stopped_reason or any(not check.passed for check in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
