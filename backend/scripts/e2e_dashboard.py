"""Exercise dashboard summary scope and counts against an explicitly configured API."""

from __future__ import annotations

import getpass
import secrets
import sys
import uuid
from typing import Any
from urllib.parse import urlencode

from e2e_refs import _record_created
from e2e_smoke import (
    ApiSession, Check, SmokeError, check_condition, check_status,
    create_test_user, parse_object, print_results, request,
)


def main() -> int:
    checks: list[Check] = []
    users: list[tuple[str, bool]] = []
    resources: list[tuple[str, str]] = []
    admin_email = getpass.getpass("Admin email: ").strip()
    admin_password = getpass.getpass("Admin password: ")
    if not admin_email or not admin_password:
        print("Admin email and password are required.")
        return 2
    admin_token = operator_token = master_token = None
    suffix = uuid.uuid4().hex
    try:
        login = request("POST", "/api/v1/auth/login", payload={"email": admin_email, "password": admin_password}, session=ApiSession())
        check_status(checks, "Admin login", login, 200)
        admin_token = parse_object(login).get("access_token")
        if not isinstance(admin_token, str):
            raise SmokeError("Admin login did not return an access token")

        user_response, operator_email, operator_password = create_test_user(admin_token, "dashboard-operator")
        operator_id = _record_created(checks, [], "Create temporary operator", user_response, "/api/v1/users")
        users.append((operator_id, False))
        op_login = request("POST", "/api/v1/auth/login", payload={"email": operator_email, "password": operator_password}, session=ApiSession())
        check_status(checks, "Operator login", op_login, 200)
        operator_token = parse_object(op_login).get("access_token")
        if not isinstance(operator_token, str):
            raise SmokeError("Operator login did not return an access token")

        def create(method: str, endpoint: str, payload: dict[str, Any], label: str) -> str:
            response = request(method, endpoint, bearer=operator_token, payload=payload)
            return _record_created(checks, resources, label, response, endpoint)

        dept = create("POST", "/api/v1/departments", {"name": f"Dashboard {suffix}", "color": "#123456"}, "Create department")
        foreign_dept = create("POST", "/api/v1/departments", {"name": f"Dashboard foreign {suffix}", "color": "#654321"}, "Create foreign department")
        own_section = create("POST", "/api/v1/sections", {"name": f"DB-{suffix[:10]}", "department_id": dept}, "Create own section")
        foreign_section = create("POST", "/api/v1/sections", {"name": f"DBF-{suffix[:10]}", "department_id": foreign_dept}, "Create foreign section")
        empty = request("GET", f"/api/v1/dashboard/summary?{urlencode({'section_id': own_section})}", bearer=operator_token)
        check_status(checks, "Dashboard empty scope returns 200", empty, 200)
        empty_data = parse_object(empty)
        empty_ok = not empty_data.get("assets") and not empty_data.get("orders") and all(point.get("pct") == 0 for point in empty_data.get("availability", []))
        check_condition(checks, "Empty scope has zero assets/orders and readiness", empty_ok, "Empty arrays and zero readiness returned" if empty_ok else "Unexpected nonzero data returned")
        work_type = create("POST", "/api/v1/work-types", {"code": f"DB-{suffix[:10]}", "name": "Dashboard test repair", "unit_type": "locomotive"}, "Create work type")
        employee = create("POST", "/api/v1/employees", {"tab_number": f"DB-{suffix[:10]}", "full_name": "Dashboard test executor", "section_id": own_section}, "Create executor")
        own_asset = create("POST", "/api/v1/fixed-assets", {"inv_number": f"DB-{suffix}", "name": f"Dashboard own {suffix[:8]}", "asset_type": "locomotive", "section_id": own_section}, "Create own asset")
        foreign_asset = create("POST", "/api/v1/fixed-assets", {"inv_number": f"DBF-{suffix}", "name": f"Dashboard foreign {suffix[:8]}", "asset_type": "locomotive", "section_id": foreign_section}, "Create foreign asset")

        def order_payload(asset_id: str, section_id: str, description: str) -> dict[str, Any]:
            return {"fixed_asset_id": asset_id, "section_id": section_id, "department_id": dept if section_id == own_section else foreign_dept,
                    "order_kind": "repair", "executor_id": employee, "description": description,
                    "repairs": [{"work_type_id": work_type, "items": []}]}

        own_order = create("POST", "/api/v1/work-orders", order_payload(own_asset, own_section, f"Dashboard pending {suffix}"), "Create own pending order")
        foreign_order = create("POST", "/api/v1/work-orders", order_payload(foreign_asset, foreign_section, f"Dashboard foreign pending {suffix}"), "Create foreign pending order")
        order_start = request("PATCH", f"/api/v1/work-orders/{own_order}", bearer=operator_token, payload={"status": "in_progress"})
        check_status(checks, "Start own work order", order_start, 200)

        summary_response = request("GET", f"/api/v1/dashboard/summary?{urlencode({'section_id': own_section})}", bearer=operator_token)
        check_status(checks, "Dashboard summary", summary_response, 200)
        summary = parse_object(summary_response)
        own_orders = summary.get("orders", [])
        own_assets = summary.get("assets", [])
        check_condition(checks, "Dashboard counts match created own records", len(own_assets) == 1 and len(own_orders) == 1, f"{len(own_assets)} asset(s), {len(own_orders)} order(s)")
        open_orders = sum(1 for order in own_orders if order.get("status") in {"pending", "in_progress"})
        check_condition(checks, "Open order count includes pending and in-progress", open_orders == 1, f"{open_orders} open order(s)")
        operational = sum(1 for asset in own_assets if asset.get("status") == "operational" and asset.get("name") not in {o.get("unit") for o in own_orders if o.get("status") in {"pending", "in_progress"}})
        on_maintenance = sum(1 for asset in own_assets if asset.get("status") == "maintenance" or (asset.get("status") == "operational" and asset.get("name") in {o.get("unit") for o in own_orders if o.get("status") in {"pending", "in_progress"}}))
        check_condition(checks, "Open order moves operational asset to maintenance", operational == 0 and on_maintenance == 1, f"operational={operational}, maintenance={on_maintenance}")

        master_email = f"dashboard-master-{suffix}@example.invalid"
        master_password = secrets.token_urlsafe(32)
        master_response = request("POST", "/api/v1/users", bearer=admin_token, payload={"email": master_email, "full_name": "Dashboard test master", "password": master_password, "role": "master", "section_id": own_section, "is_active": True})
        master_id = _record_created(checks, [], "Create temporary master", master_response, "/api/v1/users")
        users.append((master_id, True))
        master_login = request("POST", "/api/v1/auth/login", payload={"email": master_email, "password": master_password}, session=ApiSession())
        check_status(checks, "Master login", master_login, 200)
        master_token = parse_object(master_login).get("access_token")
        master_summary = request("GET", f"/api/v1/dashboard/summary?{urlencode({'section_id': foreign_section})}", bearer=master_token if isinstance(master_token, str) else None)
        check_status(checks, "Master summary ignores foreign section_id", master_summary, 200)
        master_data = parse_object(master_summary)
        master_scope_ok = all(asset.get("section") == f"DB-{suffix[:10]}" for asset in master_data.get("assets", [])) and all(order.get("section_id") == own_section for order in master_data.get("orders", []))
        check_condition(checks, "Master sees only own section", master_scope_ok and len(master_data.get("assets", [])) == 1 and all(order.get("id") != foreign_order for order in master_data.get("orders", [])), "Only own section data returned" if master_scope_ok else "Foreign section data returned")
        check_status(checks, "Dashboard requires authentication", request("GET", "/api/v1/dashboard/summary"), 401)
    except SmokeError as exc:
        print(f"Dashboard test stopped: {exc}")
    finally:
        if admin_token:
            for index, (user_id, is_master) in enumerate(users, 1):
                payload: dict[str, Any] = {"is_active": False}
                if is_master:
                    payload.update({"role": "operator", "section_id": None})
                result = request("PATCH", f"/api/v1/users/{user_id}", bearer=admin_token, payload=payload)
                check_status(checks, f"Cleanup temporary user {index}", result, 200)
            for endpoint, record_id in reversed(resources):
                response = request("DELETE", f"{endpoint}/{record_id}", bearer=admin_token)
                check_condition(checks, f"Cleanup {endpoint}", response.status in {204, 404}, f"HTTP {response.status}")
    print_results(checks)
    return 1 if any(not check.passed for check in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
