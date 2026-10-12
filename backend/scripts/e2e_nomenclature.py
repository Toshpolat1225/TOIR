"""Exercise nomenclature and norm APIs after the backend deployment is available."""

from __future__ import annotations

import getpass
import secrets
import sys
import uuid
from typing import Any

from e2e_refs import _check_item, _record_created
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


def _items(response: Any) -> list[dict[str, Any]]:
    payload = parse_object(response)
    items = payload.get("items")
    if not isinstance(items, list):
        raise SmokeError("API response did not include a paginated items list")
    return [item for item in items if isinstance(item, dict)]


def main() -> int:
    checks: list[Check] = []
    deferred_checks: list[str] = []
    users: list[str] = []
    resources: list[tuple[str, str]] = []
    admin_token: str | None = None
    operator_token: str | None = None
    master_token: str | None = None
    admin_session = ApiSession()
    suffix = uuid.uuid4().hex
    department_id: str | None = None
    foreign_department_id: str | None = None
    section_id: str | None = None
    work_type_id: str | None = None
    nomenclature_id: str | None = None
    foreign_nomenclature_id: str | None = None
    norm_id: str | None = None
    foreign_norm_id: str | None = None
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
            admin_token, "nomenclature-operator"
        )
        operator_id = _record_created(
            checks,
            [],
            "Create temporary operator",
            operator_response,
            "/api/v1/users",
        )
        users.append(operator_id)
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

        department_response = request(
            "POST",
            "/api/v1/departments",
            bearer=operator_token,
            payload={"name": f"Nomenclature test {suffix}", "color": "#123456"},
        )
        department_id = _record_created(
            checks,
            resources,
            "Create test department",
            department_response,
            "/api/v1/departments",
        )
        section_response = request(
            "POST",
            "/api/v1/sections",
            bearer=operator_token,
            payload={"name": f"NOM-{suffix[:10]}", "department_id": department_id},
        )
        section_id = _record_created(
            checks,
            resources,
            "Create master section",
            section_response,
            "/api/v1/sections",
        )

        foreign_department_response = request(
            "POST",
            "/api/v1/departments",
            bearer=operator_token,
            payload={
                "name": f"Nomenclature foreign {suffix}",
                "color": "#654321",
            },
        )
        foreign_department_id = _record_created(
            checks,
            resources,
            "Create second department",
            foreign_department_response,
            "/api/v1/departments",
        )
        work_type_response = request(
            "POST",
            "/api/v1/work-types",
            bearer=operator_token,
            payload={
                "code": f"NOM-{suffix[:12]}",
                "name": f"Nomenclature test {suffix[:8]}",
                "unit_type": "locomotive",
            },
        )
        work_type_id = _record_created(
            checks,
            resources,
            "Create test work type",
            work_type_response,
            "/api/v1/work-types",
        )

        master_email = f"nomenclature-master-{suffix}@example.invalid"
        master_password = secrets.token_urlsafe(32)
        master_response = request(
            "POST",
            "/api/v1/users",
            bearer=admin_token,
            payload={
                "email": master_email,
                "full_name": "Nomenclature test master",
                "password": master_password,
                "role": "master",
                "section_id": section_id,
                "is_active": True,
            },
        )
        master_id = _record_created(
            checks, [], "Create temporary master", master_response, "/api/v1/users"
        )
        users.append(master_id)
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

        nomenclature_response = request(
            "POST",
            "/api/v1/nomenclature",
            bearer=operator_token,
            payload={
                "department_id": department_id,
                "name": f"Test item {suffix}",
                "code": f"CODE-{suffix[:10]}",
                "unit": "шт.",
            },
        )
        nomenclature_id = _record_created(
            checks,
            resources,
            "Create nomenclature",
            nomenclature_response,
            "/api/v1/nomenclature",
        )
        foreign_nomenclature_response = request(
            "POST",
            "/api/v1/nomenclature",
            bearer=operator_token,
            payload={
                "department_id": foreign_department_id,
                "name": f"Foreign item {suffix}",
                "unit": "шт.",
            },
        )
        foreign_nomenclature_id = _record_created(
            checks,
            resources,
            "Create foreign nomenclature",
            foreign_nomenclature_response,
            "/api/v1/nomenclature",
        )
        duplicate_nomenclature = request(
            "POST",
            "/api/v1/nomenclature",
            bearer=operator_token,
            payload={
                "department_id": department_id,
                "name": f"Test item {suffix}",
                "unit": "кг",
            },
        )
        check_status(
            checks, "Duplicate department/name returns 409", duplicate_nomenclature, 409
        )

        nomenclature_list = request(
            "GET",
            f"/api/v1/nomenclature?department_id={department_id}&q={suffix[:8]}",
            bearer=operator_token,
        )
        require_status(checks, "List nomenclature by department and q", nomenclature_list, 200)
        check_condition(
            checks,
            "Nomenclature list pagination shape",
            parse_object(nomenclature_list).get("total", 0) >= 1
            and any(item.get("id") == nomenclature_id for item in _items(nomenclature_list)),
            "Filtered record appears in paginated result",
            )
        nomenclature_get = request(
            "GET",
            f"/api/v1/nomenclature/{nomenclature_id}",
            bearer=operator_token,
        )
        check_condition(
            checks,
            "Get nomenclature",
            nomenclature_get.status == 200 and _check_item(nomenclature_get, nomenclature_id),
            f"HTTP {nomenclature_get.status}",
        )
        check_status(
            checks,
            "Update nomenclature",
            request(
                "PATCH",
                f"/api/v1/nomenclature/{nomenclature_id}",
                bearer=operator_token,
                payload={"name": f"Updated item {suffix}"},
            ),
            200,
        )

        norm_response = request(
            "POST",
            "/api/v1/nomenclature-norms",
            bearer=operator_token,
            payload={
                "nomenclature_id": nomenclature_id,
                "department_id": department_id,
                "work_type_id": work_type_id,
                "standard_quantity": "2.500",
                "avg_price": "1500.00",
                "min_quantity": "1.000",
                "max_quantity": "3.000",
            },
        )
        norm_id = _record_created(
            checks,
            resources,
            "Create nomenclature norm",
            norm_response,
            "/api/v1/nomenclature-norms",
        )
        norm_payload = parse_object(norm_response)
        check_condition(
            checks,
            "Norm response includes nomenclature and work type labels",
            norm_payload.get("nomenclature_name") == f"Updated item {suffix}"
            and norm_payload.get("work_type_code") == f"NOM-{suffix[:12]}",
            "Response includes nomenclature_name and work_type_code",
        )
        duplicate_norm = request(
            "POST",
            "/api/v1/nomenclature-norms",
            bearer=operator_token,
            payload={
                "nomenclature_id": nomenclature_id,
                "department_id": department_id,
                "work_type_id": work_type_id,
                "standard_quantity": "1",
            },
        )
        check_status(
            checks,
            "Duplicate nomenclature/department/work type returns 409",
            duplicate_norm,
            409,
        )
        invalid_range = request(
            "POST",
            "/api/v1/nomenclature-norms",
            bearer=operator_token,
            payload={
                "nomenclature_id": nomenclature_id,
                "department_id": department_id,
                "work_type_id": work_type_id,
                "standard_quantity": "1",
                "min_quantity": "5",
                "max_quantity": "2",
            },
        )
        check_status(checks, "min_quantity > max_quantity is rejected", invalid_range, 422)

        foreign_norm_response = request(
            "POST",
            "/api/v1/nomenclature-norms",
            bearer=operator_token,
            payload={
                "nomenclature_id": foreign_nomenclature_id,
                "department_id": foreign_department_id,
                "work_type_id": work_type_id,
                "standard_quantity": "1",
            },
        )
        foreign_norm_id = _record_created(
            checks,
            resources,
            "Create foreign norm",
            foreign_norm_response,
            "/api/v1/nomenclature-norms",
        )
        norms_list = request(
            "GET",
            f"/api/v1/nomenclature-norms?department_id={department_id}&work_type_id={work_type_id}&nomenclature_id={nomenclature_id}",
            bearer=operator_token,
        )
        require_status(checks, "List norms with all filters", norms_list, 200)
        check_condition(
            checks,
            "Norm list pagination shape",
            parse_object(norms_list).get("total") == 1
            and _items(norms_list)[0].get("id") == norm_id,
            "Filtered norm appears in paginated result",
        )
        check_condition(
            checks,
            "Get nomenclature norm",
            (norm_get := request(
                "GET",
                f"/api/v1/nomenclature-norms/{norm_id}",
                bearer=operator_token,
            )).status == 200
            and _check_item(norm_get, norm_id),
            f"HTTP {norm_get.status}",
        )
        check_status(
            checks,
            "Update nomenclature norm",
            request(
                "PATCH",
                f"/api/v1/nomenclature-norms/{norm_id}",
                bearer=operator_token,
                payload={"standard_quantity": "2.750"},
            ),
            200,
        )

        master_nomenclature_list = request(
            "GET", "/api/v1/nomenclature?limit=1000", bearer=master_token
        )
        master_nomenclature_ids = {
            item.get("id") for item in _items(master_nomenclature_list)
        }
        check_condition(
            checks,
            "Master nomenclature is limited to own department",
            master_nomenclature_list.status == 200
            and nomenclature_id in master_nomenclature_ids
            and foreign_nomenclature_id not in master_nomenclature_ids,
            "Own department record only",
        )
        check_status(
            checks,
            "Master cannot read foreign nomenclature",
            request(
                "GET",
                f"/api/v1/nomenclature/{foreign_nomenclature_id}",
                bearer=master_token,
            ),
            404,
        )
        master_norm_list = request(
            "GET", "/api/v1/nomenclature-norms?limit=1000", bearer=master_token
        )
        master_norm_ids = {item.get("id") for item in _items(master_norm_list)}
        check_condition(
            checks,
            "Master norms are limited to own department",
            master_norm_list.status == 200
            and norm_id in master_norm_ids
            and foreign_norm_id not in master_norm_ids,
            "Own department norm only",
        )
        check_status(
            checks,
            "Master cannot write nomenclature",
            request(
                "POST",
                "/api/v1/nomenclature",
                bearer=master_token,
                payload={
                    "department_id": department_id,
                    "name": f"Forbidden {suffix}",
                },
            ),
            403,
        )

        # Work-order routes are intentionally outside this T2b change. This
        # conflict is checked after T4 exposes a public way to attach test items.
        deferred_checks.append(
            "Delete a nomenclature linked to work_order_items returns 409 "
            "(deferred until the T4 work-order API can create the fixture)"
        )

        check_status(
            checks,
            "Delete nomenclature norm",
            request(
                "DELETE",
                f"/api/v1/nomenclature-norms/{norm_id}",
                bearer=operator_token,
            ),
            204,
        )
        resources.remove(("/api/v1/nomenclature-norms", norm_id))
        check_status(
            checks,
            "Delete foreign nomenclature norm",
            request(
                "DELETE",
                f"/api/v1/nomenclature-norms/{foreign_norm_id}",
                bearer=operator_token,
            ),
            204,
        )
        resources.remove(("/api/v1/nomenclature-norms", foreign_norm_id))
        check_status(
            checks,
            "Delete nomenclature",
            request(
                "DELETE",
                f"/api/v1/nomenclature/{nomenclature_id}",
                bearer=operator_token,
            ),
            204,
        )
        resources.remove(("/api/v1/nomenclature", nomenclature_id))
        check_status(
            checks,
            "Delete foreign nomenclature",
            request(
                "DELETE",
                f"/api/v1/nomenclature/{foreign_nomenclature_id}",
                bearer=operator_token,
            ),
            204,
        )
        resources.remove(("/api/v1/nomenclature", foreign_nomenclature_id))

    except SmokeError as exc:
        stopped_reason = str(exc)
    finally:
        if admin_token is not None:
            for index, user_id in enumerate(users, start=1):
                response = request(
                    "PATCH",
                    f"/api/v1/users/{user_id}",
                    bearer=admin_token,
                    payload={"is_active": False},
                )
                check_status(checks, f"Cleanup: deactivate test user {index}", response, 200)
            for endpoint, record_id in reversed(resources):
                response = request(
                    "DELETE",
                    f"{endpoint}/{record_id}",
                    bearer=admin_token,
                )
                check_condition(
                    checks,
                    f"Cleanup: {endpoint.rsplit('/', 1)[-1]}",
                    response.status in {204, 404},
                    f"HTTP {response.status}",
                )

    if stopped_reason:
        print(f"\nNomenclature test stopped: {stopped_reason}")
    print_results(checks)
    if deferred_checks:
        print("\nKechiktirilgan tekshiruvlar (bajarilmadi)")
        for item in deferred_checks:
            print(f"- {item}")
    return 1 if stopped_reason or any(not item.passed for item in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
