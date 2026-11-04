"""Exercise Wialon-unit and unified-asset APIs against a deployed test API.

Requires at least one unit previously fetched into wialon_units. Use a disposable
test database; the script creates temporary users, a section, and a fixed asset.
"""

from __future__ import annotations

import getpass
import secrets
import sys
import uuid
from typing import Any
from urllib.parse import quote, urlencode

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


def _items(response: Any) -> list[dict[str, Any]]:
    payload = parse_object(response)
    items = payload.get("items")
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise SmokeError("API returned an unexpected paginated response")
    return items


def main() -> int:
    checks: list[Check] = []
    users: list[tuple[str, bool]] = []
    resources: list[tuple[str, str]] = []
    admin_token: str | None = None
    operator_token: str | None = None
    unit_id: str | None = None
    asset_id: str | None = None
    section_id: str | None = None
    stopped_reason: str | None = None
    suffix = uuid.uuid4().hex

    admin_email = getpass.getpass("Admin email: ").strip()
    admin_password = getpass.getpass("Admin password: ")
    if not admin_email or not admin_password:
        print("Admin credentials are required.")
        return 2

    try:
        admin_login = request(
            "POST",
            "/api/v1/auth/login",
            payload={"email": admin_email, "password": admin_password},
            session=ApiSession(),
        )
        require_status(checks, "Admin login", admin_login, 200)
        admin_token = parse_object(admin_login).get("access_token")
        if not isinstance(admin_token, str) or not admin_token:
            raise SmokeError("Admin login response did not include an access token")

        operator_response, operator_email, operator_password = create_test_user(
            admin_token, "wialon-units"
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

        section_response = request(
            "POST",
            "/api/v1/sections",
            bearer=operator_token,
            payload={"name": f"WIALON-E2E-{suffix[:10]}"},
        )
        section_id = _record_created(
            checks, resources, "Create test section", section_response, "/api/v1/sections"
        )
        master_email = f"wialon-master-{suffix}@example.invalid"
        master_password = secrets.token_urlsafe(32)
        master_response = request(
            "POST",
            "/api/v1/users",
            bearer=admin_token,
            payload={
                "email": master_email,
                "full_name": "Wialon unit test master",
                "password": master_password,
                "role": "master",
                "section_id": section_id,
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

        unlinked = request(
            "GET",
            "/api/v1/wialon/units?linked=false&limit=1000&offset=0",
            bearer=admin_token,
        )
        require_status(checks, "List unlinked Wialon units", unlinked, 200)
        unlinked_items = _items(unlinked)
        if not unlinked_items:
            raise SmokeError(
                "No unlinked Wialon unit exists; run a test sync before this E2E script"
            )
        unit_id_value = unlinked_items[0].get("unit_id")
        if not isinstance(unit_id_value, str) or not unit_id_value:
            raise SmokeError("Wialon unit response is missing unit_id")
        unit_id = unit_id_value
        encoded_unit_id = quote(unit_id, safe="")

        detail = request(
            "GET",
            f"/api/v1/wialon/units/{encoded_unit_id}",
            bearer=admin_token,
        )
        detail_body = parse_object(detail)
        check_condition(
            checks,
            "Get Wialon unit detail",
            detail.status == 200
            and detail_body.get("unit_id") == unit_id
            and isinstance(detail_body.get("rejected_readings"), list),
            "Unit and rejected-reading fields are returned"
            if detail.status == 200
            and detail_body.get("unit_id") == unit_id
            and isinstance(detail_body.get("rejected_readings"), list)
            else f"HTTP {detail.status}; invalid detail response",
        )
        suggestions = request(
            "GET",
            f"/api/v1/wialon/units/{encoded_unit_id}/suggestions",
            bearer=admin_token,
        )
        suggestions_body = parse_object(suggestions)
        check_condition(
            checks,
            "Get Wialon asset suggestions",
            suggestions.status == 200
            and isinstance(suggestions_body.get("items"), list),
            "Suggestions are returned without creating a link"
            if suggestions.status == 200
            and isinstance(suggestions_body.get("items"), list)
            else f"HTTP {suggestions.status}; invalid suggestion response",
        )

        unified_before = request(
            "GET",
            f"/api/v1/fixed-assets/unified?source=wialon&{urlencode({'q': unit_id})}",
            bearer=admin_token,
        )
        check_condition(
            checks,
            "Unified view includes Wialon-only unit",
            unified_before.status == 200
            and any(
                item.get("unit_id") == unit_id and item.get("source") == "wialon"
                for item in _items(unified_before)
            ),
            "Unlinked unit is represented as Wialon-only"
            if unified_before.status == 200
            else f"HTTP {unified_before.status}",
        )

        invalid_type = request(
            "POST",
            f"/api/v1/wialon/units/{encoded_unit_id}/create-asset",
            bearer=operator_token,
            payload={
                "inv_number": f"WIALON-E2E-BAD-{suffix}",
                "asset_type": "unsupported",
            },
        )
        check_status(checks, "Reject unsupported asset type", invalid_type, 422)

        create_asset = request(
            "POST",
            f"/api/v1/wialon/units/{encoded_unit_id}/create-asset",
            bearer=operator_token,
            payload={
                "inv_number": f"WIALON-E2E-{suffix}",
                "asset_type": "diesel",
                "series": "WIALON-E2E-DIESEL",
                "number": number_suffix,
                "section_id": section_id,
            },
        )
        require_status(checks, "Create linked fixed asset", create_asset, 201)
        create_body = parse_object(create_asset)
        asset = create_body.get("asset")
        if not isinstance(asset, dict) or not isinstance(asset.get("id"), str):
            raise SmokeError("Create-asset response did not include an asset ID")
        asset_id = asset["id"]
        resources.append(("/api/v1/fixed-assets", asset_id))
        check_condition(
            checks,
            "Created asset keeps the explicit Wialon link",
            asset.get("wialon_id") == unit_id,
            "Created fixed asset is linked to the requested unit"
            if asset.get("wialon_id") == unit_id
            else "Response wialon_id did not match",
        )
        if detail_body.get("suspect_absolute") is True:
            check_condition(
                checks,
                "Suspect counter creates zero-mileage asset",
                asset.get("mileage") in (0, "0", "0.00")
                and isinstance(create_body.get("warning"), str),
                "Suspect mileage is set to zero with a warning"
                if asset.get("mileage") in (0, "0", "0.00")
                and isinstance(create_body.get("warning"), str)
                else "Expected zero mileage and a warning",
            )

        duplicate = request(
            "POST",
            f"/api/v1/wialon/units/{encoded_unit_id}/create-asset",
            bearer=operator_token,
            payload={
                "inv_number": f"WIALON-E2E-DUP-{suffix}",
                "asset_type": "diesel",
            },
        )
        check_status(checks, "Reject duplicate Wialon link", duplicate, 409)

        linked_detail = request(
            "GET",
            f"/api/v1/wialon/units/{encoded_unit_id}",
            bearer=admin_token,
        )
        linked_body = parse_object(linked_detail)
        check_condition(
            checks,
            "Unit detail shows linked asset",
            linked_detail.status == 200
            and isinstance(linked_body.get("linked_asset"), dict)
            and linked_body["linked_asset"].get("id") == asset_id,
            "Wialon unit resolves to the newly created fixed asset"
            if linked_detail.status == 200
            and isinstance(linked_body.get("linked_asset"), dict)
            and linked_body["linked_asset"].get("id") == asset_id
            else f"HTTP {linked_detail.status}; link missing",
        )
        linked_list = request(
            "GET",
            f"/api/v1/wialon/units?linked=true&{urlencode({'q': unit_id})}",
            bearer=admin_token,
        )
        check_condition(
            checks,
            "Unit list returns linked asset summary",
            linked_list.status == 200
            and any(
                item.get("unit_id") == unit_id
                and isinstance(item.get("linked_asset"), dict)
                for item in _items(linked_list)
            ),
            "Linked unit appears in the filtered list"
            if linked_list.status == 200
            else f"HTTP {linked_list.status}",
        )
        unified_both = request(
            "GET",
            f"/api/v1/fixed-assets/unified?source=both&{urlencode({'q': unit_id})}",
            bearer=master_token,
        )
        check_condition(
            checks,
            "Master sees own linked unified row",
            unified_both.status == 200
            and any(
                item.get("asset_id") == asset_id and item.get("source") == "both"
                for item in _items(unified_both)
            ),
            "Master receives the row from the assigned section"
            if unified_both.status == 200
            else f"HTTP {unified_both.status}",
        )

        unlink = request(
            "PATCH",
            f"/api/v1/fixed-assets/{asset_id}",
            bearer=operator_token,
            payload={"wialon_id": None},
        )
        check_status(checks, "Unlink Wialon unit", unlink, 200)
        master_wialon_only = request(
            "GET",
            "/api/v1/fixed-assets/unified?source=wialon&limit=1000&offset=0",
            bearer=master_token,
        )
        master_units = request(
            "GET",
            "/api/v1/wialon/units?linked=false&limit=1000&offset=0",
            bearer=master_token,
        )
        master_detail = request(
            "GET",
            f"/api/v1/wialon/units/{encoded_unit_id}",
            bearer=master_token,
        )
        check_condition(
            checks,
            "Master cannot see Wialon-only unit",
            master_wialon_only.status == 200
            and not _items(master_wialon_only),
            "Unified Wialon-only result is empty for master"
            if master_wialon_only.status == 200
            else f"HTTP {master_wialon_only.status}",
        )
        check_condition(
            checks,
            "Master Wialon list excludes unlinked unit",
            master_units.status == 200
            and all(item.get("unit_id") != unit_id for item in _items(master_units)),
            "Unlinked unit is not visible to master"
            if master_units.status == 200
            else f"HTTP {master_units.status}",
        )
        check_status(checks, "Master detail for unlinked unit is hidden", master_detail, 404)

    except SmokeError as exc:
        stopped_reason = str(exc)
    finally:
        if admin_token is not None:
            for index, (user_id, is_master) in enumerate(users, start=1):
                user_payload: dict[str, Any] = {"is_active": False}
                if is_master:
                    user_payload.update({"role": "operator", "section_id": None})
                response = request(
                    "PATCH",
                    f"/api/v1/users/{user_id}",
                    bearer=admin_token,
                    payload=user_payload,
                )
                check_status(
                    checks, f"Cleanup: deactivate temporary user {index}", response, 200
                )
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
        print(f"\nWialon unit test stopped: {stopped_reason}")
    print_results(checks)
    return 1 if stopped_reason or any(not item.passed for item in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
