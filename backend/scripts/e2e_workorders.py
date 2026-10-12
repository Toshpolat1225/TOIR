"""Exercise work-order endpoints against the deployed API after deployment."""

from __future__ import annotations

import getpass
import re
import secrets
import sys
import uuid
from typing import Any
from urllib.parse import urlencode

from e2e_refs import _record_created
from e2e_smoke import (
    ApiSession,
    Check,
    SmokeError,
    check_condition,
    check_status,
    create_test_user,
    parse_object,
    print_results,
    request,
    require_status,
)


def _record_id(response: Any) -> str:
    value = parse_object(response).get("id")
    if not isinstance(value, str):
        raise SmokeError("API response did not include a record id")
    return value


def main() -> int:
    checks: list[Check] = []
    users: list[tuple[str, bool]] = []
    resources: list[tuple[str, str]] = []
    admin_token: str | None = None
    operator_token: str | None = None
    master_token: str | None = None
    operator_id: str | None = None
    master_id: str | None = None
    own_department_id: str | None = None
    own_section_id: str | None = None
    foreign_section_id: str | None = None
    work_type_id: str | None = None
    employee_id: str | None = None
    asset_id: str | None = None
    foreign_asset_id: str | None = None
    nomenclature_id: str | None = None
    admin_session = ApiSession()
    suffix = uuid.uuid4().hex
    stopped_reason: str | None = None
    admin_email = getpass.getpass("Admin email: ").strip()
    admin_password = getpass.getpass("Admin password: ")
    if not admin_email or not admin_password:
        print("Admin email and password are required.")
        return 2

    try:
        login = request(
            "POST",
            "/api/v1/auth/login",
            payload={"email": admin_email, "password": admin_password},
            session=admin_session,
        )
        require_status(checks, "Admin login", login, 200)
        admin_token = parse_object(login).get("access_token")
        if not isinstance(admin_token, str) or not admin_token:
            raise SmokeError("Admin login response did not include an access token")

        operator_response, operator_email, operator_password = create_test_user(
            admin_token, "work-orders-operator"
        )
        operator_id = _record_created(
            checks, [], "Create temporary operator", operator_response, "/api/v1/users"
        )
        users.append((operator_id, False))
        operator_login = request(
            "POST",
            "/api/v1/auth/login",
            payload={"email": operator_email, "password": operator_password},
            session=ApiSession(),
        )
        require_status(checks, "Operator login", operator_login, 200)
        operator_token = parse_object(operator_login).get("access_token")
        if not isinstance(operator_token, str) or not operator_token:
            raise SmokeError("Operator login response did not include an access token")

        own_department = request(
            "POST",
            "/api/v1/departments",
            bearer=operator_token,
            payload={"name": f"Work order test {suffix}", "color": "#123456"},
        )
        own_department_id = _record_created(
            checks, resources, "Create department", own_department, "/api/v1/departments"
        )
        own_section = request(
            "POST",
            "/api/v1/sections",
            bearer=operator_token,
            payload={"name": f"WO-{suffix[:12]}", "department_id": own_department_id},
        )
        own_section_id = _record_created(
            checks, resources, "Create own section", own_section, "/api/v1/sections"
        )
        foreign_department = request(
            "POST",
            "/api/v1/departments",
            bearer=operator_token,
            payload={"name": f"Work order foreign {suffix}", "color": "#654321"},
        )
        foreign_department_id = _record_created(
            checks, resources, "Create foreign department", foreign_department,
            "/api/v1/departments",
        )
        foreign_section = request(
            "POST",
            "/api/v1/sections",
            bearer=operator_token,
            payload={
                "name": f"WO-FOREIGN-{suffix[:8]}",
                "department_id": foreign_department_id,
            },
        )
        foreign_section_id = _record_created(
            checks, resources, "Create foreign section", foreign_section, "/api/v1/sections"
        )

        master_email = f"work-orders-master-{suffix}@example.invalid"
        master_password = secrets.token_urlsafe(32)
        master_response = request(
            "POST",
            "/api/v1/users",
            bearer=admin_token,
            payload={
                "email": master_email,
                "full_name": "Work order test master",
                "password": master_password,
                "role": "master",
                "section_id": own_section_id,
                "is_active": True,
            },
        )
        master_id = _record_created(
            checks, [], "Create temporary master", master_response, "/api/v1/users"
        )
        users.append((master_id, True))
        master_login = request(
            "POST",
            "/api/v1/auth/login",
            payload={"email": master_email, "password": master_password},
            session=ApiSession(),
        )
        require_status(checks, "Master login", master_login, 200)
        master_token = parse_object(master_login).get("access_token")
        if not isinstance(master_token, str) or not master_token:
            raise SmokeError("Master login response did not include an access token")

        type_response = request(
            "POST",
            "/api/v1/work-types",
            bearer=operator_token,
            payload={
                "code": f"WO-{suffix[:12]}",
                "name": "Work order E2E repair",
                "unit_type": "locomotive",
            },
        )
        work_type_id = _record_created(
            checks, resources, "Create work type", type_response, "/api/v1/work-types"
        )
        employee_response = request(
            "POST",
            "/api/v1/employees",
            bearer=operator_token,
            payload={
                "tab_number": f"WO-{suffix[:12]}",
                "full_name": "Work order E2E executor",
                "section_id": own_section_id,
            },
        )
        employee_id = _record_created(
            checks, resources, "Create executor", employee_response, "/api/v1/employees"
        )
        asset_response = request(
            "POST",
            "/api/v1/fixed-assets",
            bearer=operator_token,
            payload={
                "inv_number": f"WO-{suffix}",
                "name": f"Work order unit {suffix[:8]}",
                "asset_type": "locomotive",
                "section_id": own_section_id,
                "mileage": "1234.50",
            },
        )
        asset_id = _record_created(
            checks, resources, "Create own fixed asset", asset_response,
            "/api/v1/fixed-assets",
        )
        foreign_asset_response = request(
            "POST",
            "/api/v1/fixed-assets",
            bearer=operator_token,
            payload={
                "inv_number": f"WO-FOREIGN-{suffix}",
                "name": f"Foreign work order unit {suffix[:8]}",
                "asset_type": "diesel",
                "section_id": foreign_section_id,
            },
        )
        foreign_asset_id = _record_created(
            checks, resources, "Create foreign fixed asset", foreign_asset_response,
            "/api/v1/fixed-assets",
        )
        nomenclature_response = request(
            "POST",
            "/api/v1/nomenclature",
            bearer=operator_token,
            payload={
                "department_id": own_department_id,
                "name": f"Work order item {suffix}",
                "code": f"WO-{suffix[:12]}",
                "unit": "шт.",
            },
        )
        nomenclature_id = _record_created(
            checks, resources, "Create nomenclature", nomenclature_response,
            "/api/v1/nomenclature",
        )
        norm_response = request(
            "POST",
            "/api/v1/nomenclature-norms",
            bearer=operator_token,
            payload={
                "department_id": own_department_id,
                "nomenclature_id": nomenclature_id,
                "work_type_id": work_type_id,
                "standard_quantity": "1",
                "avg_price": "12.50",
            },
        )
        norm_id = _record_created(
            checks, resources, "Create norm", norm_response,
            "/api/v1/nomenclature-norms",
        )
        template_response = request(
            "POST",
            "/api/v1/work-type-templates",
            bearer=operator_token,
            payload={
                "work_type_id": work_type_id,
                "department_id": own_department_id,
                "nomenclature_id": nomenclature_id,
                "default_quantity": "1",
                "is_required": True,
            },
        )
        _record_created(
            checks, resources, "Create work type template", template_response,
            "/api/v1/work-type-templates",
        )

        def order_payload(
            description: str,
            *,
            target_asset: str = asset_id or "",
            target_section: str = own_section_id or "",
            item_nomenclature: str = nomenclature_id or "",
            date_end: str | None = None,
        ) -> dict[str, Any]:
            return {
                "fixed_asset_id": target_asset,
                "section_id": target_section,
                "department_id": own_department_id,
                "order_kind": "repair",
                "executor_id": employee_id,
                "description": description,
                "date_end": date_end,
                "repairs": [
                    {
                        "work_type_id": work_type_id,
                        "items": [
                            {
                                "nomenclature_id": item_nomenclature,
                                "name": f"Item {suffix}",
                                "inv_no": f"INV-{suffix[:8]}",
                                "unit": "шт.",
                                "qty": "2",
                                "note": "E2E",
                            }
                        ],
                    }
                ],
            }

        primary_description = f"Nested transaction work-order {suffix}"
        primary_response = request(
            "POST",
            "/api/v1/work-orders",
            bearer=operator_token,
            payload=order_payload(primary_description),
        )
        primary_id = _record_created(
            checks, resources, "Create work order with nested repairs/items",
            primary_response, "/api/v1/work-orders",
        )
        primary = parse_object(primary_response)
        check_condition(
            checks,
            "Generated work-order number format",
            bool(re.fullmatch(r"НЗ-\d{8}-\d{6}", str(primary.get("number", "")))),
            str(primary.get("number", "Missing number")),
        )
        nested_repairs = primary.get("repairs")
        nested_ok = (
            isinstance(nested_repairs, list)
            and len(nested_repairs) == 1
            and nested_repairs[0].get("work_type_id") == work_type_id
            and len(nested_repairs[0].get("items", [])) == 1
        )
        check_condition(
            checks,
            "Nested repair and item returned",
            nested_ok,
            "Work order response includes the repair and item"
            if nested_ok
            else "Nested repair or item is missing",
        )
        check_condition(
            checks,
            "Mileage snapshot is server-derived",
            str(primary.get("mileage_at_creation")) == "1234.50",
            str(primary.get("mileage_at_creation")),
        )

        before_bad_create = request(
            "GET",
            f"/api/v1/work-orders?{urlencode({'q': f'atomic-failure-{suffix}'})}",
            bearer=operator_token,
        )
        require_status(checks, "Query before failed transaction", before_bad_create, 200)
        invalid_create = request(
            "POST",
            "/api/v1/work-orders",
            bearer=operator_token,
            payload=order_payload(
                f"atomic-failure-{suffix}",
                item_nomenclature=str(uuid.uuid4()),
            ),
        )
        check_status(checks, "Invalid nested item is rejected", invalid_create, 409)
        after_bad_create = request(
            "GET",
            f"/api/v1/work-orders?{urlencode({'q': f'atomic-failure-{suffix}'})}",
            bearer=operator_token,
        )
        empty_after_failure = (
            after_bad_create.status == 200
            and parse_object(after_bad_create).get("total") == 0
        )
        check_condition(
            checks,
            "Failed nested create leaves no partial work order",
            empty_after_failure,
            "No work order persisted after the failed transaction"
            if empty_after_failure
            else "A partial work order was persisted",
        )

        check_status(
            checks,
            "List work orders with query filter",
            request(
                "GET",
                f"/api/v1/work-orders?{urlencode({'q': primary_description})}",
                bearer=operator_token,
            ),
            200,
        )
        check_status(
            checks,
            "List open work orders",
            request("GET", "/api/v1/work-orders?open=true", bearer=operator_token),
            200,
        )
        check_status(
            checks,
            "List by section and asset",
            request(
                "GET",
                f"/api/v1/work-orders?section_id={own_section_id}&fixed_asset_id={asset_id}",
                bearer=operator_token,
            ),
            200,
        )
        check_status(
            checks,
            "List by multiple statuses and date range",
            request(
                "GET",
                f"/api/v1/work-orders?{urlencode({'status': 'completed,cancelled', 'date_from': '2000-01-01T00:00:00Z', 'date_to': '2100-01-01T00:00:00Z'})}",
                bearer=operator_token,
            ),
            200,
        )
        get_primary = request(
            "GET", f"/api/v1/work-orders/{primary_id}", bearer=operator_token
        )
        check_status(checks, "Get work order", get_primary, 200)
        check_status(
            checks,
            "Patch work-order note",
            request(
                "PATCH",
                f"/api/v1/work-orders/{primary_id}",
                bearer=operator_token,
                payload={"note": "updated by E2E"},
            ),
            200,
        )
        check_status(
            checks,
            "Replace repairs and items",
            request(
                "PATCH",
                f"/api/v1/work-orders/{primary_id}",
                bearer=operator_token,
                payload={
                    "repairs": [
                        {
                            "work_type_id": work_type_id,
                            "items": [
                                {
                                    "name": f"Replacement item {suffix}",
                                    "qty": "3",
                                }
                            ],
                        }
                    ]
                },
            ),
            200,
        )
        check_status(
            checks,
            "Start work order",
            request(
                "PATCH",
                f"/api/v1/work-orders/{primary_id}",
                bearer=operator_token,
                payload={"status": "in_progress"},
            ),
            200,
        )
        check_status(
            checks,
            "Complete in-progress work order",
            request(
                "PATCH",
                f"/api/v1/work-orders/{primary_id}",
                bearer=operator_token,
                payload={"status": "completed"},
            ),
            200,
        )
        check_status(
            checks,
            "Completed work order cannot be edited",
            request(
                "PATCH",
                f"/api/v1/work-orders/{primary_id}",
                bearer=operator_token,
                payload={"note": "must fail"},
            ),
            409,
        )

        invalid_transition = request(
            "PATCH",
            f"/api/v1/work-orders/{primary_id}",
            bearer=operator_token,
            payload={"status": "pending"},
        )
        check_status(checks, "Invalid status transition returns 409", invalid_transition, 409)

        overdue_response = request(
            "POST",
            "/api/v1/work-orders",
            bearer=operator_token,
            payload=order_payload(
                f"overdue-check-{suffix}", date_end="2000-01-01T00:00:00Z"
            ),
        )
        overdue_id = _record_created(
            checks, resources, "Create overdue work order", overdue_response,
            "/api/v1/work-orders",
        )
        check_condition(
            checks,
            "Overdue is calculated from date_end",
            parse_object(overdue_response).get("is_overdue") is True,
            "Open work order with past date_end is overdue"
            if parse_object(overdue_response).get("is_overdue") is True
            else "is_overdue was not calculated",
        )
        pending_to_completed = request(
            "PATCH",
            f"/api/v1/work-orders/{overdue_id}",
            bearer=operator_token,
            payload={"status": "completed"},
        )
        check_status(checks, "Pending cannot jump directly to completed", pending_to_completed, 409)
        check_status(
            checks,
            "Cancel pending work order",
            request(
                "PATCH",
                f"/api/v1/work-orders/{overdue_id}",
                bearer=operator_token,
                payload={"status": "cancelled"},
            ),
            200,
        )

        master_order_response = request(
            "POST",
            "/api/v1/work-orders",
            bearer=master_token,
            payload=order_payload(f"master-own-{suffix}"),
        )
        master_order_id = _record_created(
            checks, resources, "Master creates within own section",
            master_order_response, "/api/v1/work-orders",
        )
        check_status(
            checks,
            "Master cannot create in another section",
            request(
                "POST",
                "/api/v1/work-orders",
                bearer=master_token,
                payload=order_payload(
                    f"master-foreign-{suffix}",
                    target_asset=foreign_asset_id,
                    target_section=foreign_section_id,
                ),
            ),
            403,
        )
        check_status(
            checks,
            "Master cannot read another section order",
            request(
                "GET",
                f"/api/v1/work-orders/{overdue_id}",
                bearer=master_token,
            ),
            404,
        )
        master_list = request(
            "GET",
            "/api/v1/work-orders?limit=1000",
            bearer=master_token,
        )
        master_items = parse_object(master_list).get("items", [])
        own_only = (
            master_list.status == 200
            and isinstance(master_items, list)
            and all(item.get("section_id") == own_section_id for item in master_items)
        )
        check_condition(
            checks,
            "Master list is restricted to own section",
            own_only,
            "All returned work orders belong to the master section"
            if own_only
            else "A work order outside the master section was returned",
        )
        check_status(
            checks,
            "Master can update own work order",
            request(
                "PATCH",
                f"/api/v1/work-orders/{master_order_id}",
                bearer=master_token,
                payload={"note": "master update"},
            ),
            200,
        )
        check_status(
            checks,
            "Master cannot update another section order",
            request(
                "PATCH",
                f"/api/v1/work-orders/{overdue_id}",
                bearer=master_token,
                payload={"note": "foreign update"},
            ),
            404,
        )

        norm_check = request(
            "POST",
            "/api/v1/work-orders/norm-check",
            bearer=operator_token,
            payload={
                "department_id": own_department_id,
                "items": [
                    {
                        "nomenclature_id": nomenclature_id,
                        "work_type_id": work_type_id,
                        "qty": "2",
                    }
                ],
            },
        )
        norm_check_data = norm_check.json() if norm_check.status == 200 else []
        norm_list = norm_check_data if isinstance(norm_check_data, list) else []
        norm_valid = (
            norm_check.status == 200
            and len(norm_list) == 1
            and norm_list[0].get("warning") is True
            and str(norm_list[0].get("estimated_cost")) == "25.00"
        )
        check_condition(
            checks,
            "Norm check reports overrun and estimated cost",
            norm_valid,
            "Warning and qty × average price were returned"
            if norm_valid
            else f"HTTP {norm_check.status}; unexpected norm-check result",
        )
        templates = request(
            "GET",
            f"/api/v1/work-orders/template-items?work_type_id={work_type_id}&department_id={own_department_id}",
            bearer=operator_token,
        )
        check_condition(
            checks,
            "Template items are returned",
            templates.status == 200
            and isinstance(templates.json(), list)
            and bool(templates.json()),
            f"HTTP {templates.status}; template rows returned"
            if templates.status == 200
            else f"HTTP {templates.status}",
        )

        check_status(
            checks,
            "Delete nomenclature referenced by work order returns 409",
            request(
                "DELETE",
                f"/api/v1/nomenclature/{nomenclature_id}",
                bearer=operator_token,
            ),
            409,
        )
    except SmokeError as exc:
        stopped_reason = str(exc)
    finally:
        if admin_token is not None:
            for index, (user_id, is_master) in enumerate(users, start=1):
                cleanup_payload: dict[str, Any] = {"is_active": False}
                if is_master:
                    cleanup_payload.update({"role": "operator", "section_id": None})
                response = request(
                    "PATCH",
                    f"/api/v1/users/{user_id}",
                    bearer=admin_token,
                    payload=cleanup_payload,
                )
                check_status(checks, f"Cleanup: deactivate temporary user {index}", response, 200)
            for endpoint, record_id in reversed(resources):
                response = request(
                    "DELETE", f"{endpoint}/{record_id}", bearer=admin_token
                )
                cleanup_ok = response.status in {204, 404}
                check_condition(
                    checks,
                    f"Cleanup: {endpoint.rsplit('/', 1)[-1]}",
                    cleanup_ok,
                    f"HTTP {response.status}",
                )

    if stopped_reason:
        print(f"\nWork-order test stopped: {stopped_reason}")
    print_results(checks)
    return 1 if stopped_reason or any(not item.passed for item in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
