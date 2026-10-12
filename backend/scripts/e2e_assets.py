"""Exercise fixed-asset, mileage, and Wialon endpoints against the API tunnel.

Run only after deploying the backend changes and configuring the API tunnel.
"""

from __future__ import annotations

import getpass
import os
import secrets
import sys
import uuid
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
    create_test_user,
    parse_object,
    print_results,
    request,
    require_status,
)


def _record_ok(response: Any, expected_id: str) -> bool:
    try:
        return response.status == 200 and parse_object(response).get("id") == expected_id
    except SmokeError:
        return False


def _check_history(
    checks: list[Check],
    label: str,
    response: Any,
    source: str,
    expected_mileage: str,
) -> None:
    try:
        payload = parse_object(response)
        items = payload.get("items")
        valid = (
            response.status == 200
            and isinstance(items, list)
            and any(
                item.get("source") == source
                and Decimal(str(item.get("mileage"))) == Decimal(expected_mileage)
                for item in items
                if isinstance(item, dict)
            )
        )
    except SmokeError:
        valid = False
    check_condition(
        checks,
        label,
        valid,
        "Expected mileage history record is present"
        if valid
        else f"HTTP {response.status}; expected {source} history at {expected_mileage}",
    )


def main() -> int:
    checks: list[Check] = []
    users: list[tuple[str, bool]] = []
    resources: list[tuple[str, str]] = []
    admin_token: str | None = None
    operator_token: str | None = None
    master_token: str | None = None
    admin_session = ApiSession()

    admin_email = getpass.getpass("Admin email: ").strip()
    admin_password = getpass.getpass("Admin password: ")
    ingest_token = os.environ.get("WIALON_INGEST_TOKEN") or getpass.getpass("Wialon ingest token: ")
    if not admin_email or not admin_password or not ingest_token:
        print("Admin credentials and the Wialon ingest token are required.")
        return 2

    suffix = uuid.uuid4().hex
    number_suffix = str(secrets.randbelow(9000) + 1000)
    operator_id: str | None = None
    master_id: str | None = None
    own_section_id: str | None = None
    other_section_id: str | None = None
    stopped_reason: str | None = None

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
            admin_token, "assets-operator"
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

        own_section_response = request(
            "POST",
            "/api/v1/sections",
            bearer=operator_token,
            payload={"name": f"ASSET-OWN-{suffix[:10]}"},
        )
        own_section_id = _record_created(
            checks, resources, "Create assigned section", own_section_response, "/api/v1/sections"
        )
        other_section_response = request(
            "POST",
            "/api/v1/sections",
            bearer=operator_token,
            payload={"name": f"ASSET-OTHER-{suffix[:10]}"},
        )
        other_section_id = _record_created(
            checks, resources, "Create other section", other_section_response, "/api/v1/sections"
        )

        master_email = f"assets-master-{suffix}@example.invalid"
        master_password = secrets.token_urlsafe(32)
        master_response = request(
            "POST",
            "/api/v1/users",
            bearer=admin_token,
            payload={
                "email": master_email,
                "full_name": "Fixed asset test master",
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

        inv_number = f"ASSET-{suffix}"
        wialon_id = f"w-{suffix}"
        asset_response = request(
            "POST",
            "/api/v1/fixed-assets",
            bearer=operator_token,
            payload={
                "inv_number": inv_number,
                "name": "Reference Wialon Unit",
                "asset_type": "locomotive",
                "series": "TEST",
                "depot": "ASSET TEST",
                "section_id": own_section_id,
                "status": "operational",
                "mileage": 100,
                "wialon_id": wialon_id,
            },
        )
        asset_id = _record_created(
            checks, resources, "Create fixed asset", asset_response, "/api/v1/fixed-assets"
        )
        other_asset_response = request(
            "POST",
            "/api/v1/fixed-assets",
            bearer=operator_token,
            payload={
                "inv_number": f"ASSET-FOREIGN-{suffix}",
                "name": "Foreign reference asset",
                "asset_type": "wagon",
                "section_id": other_section_id,
            },
        )
        other_asset_id = _record_created(
            checks,
            resources,
            "Create fixed asset in another section",
            other_asset_response,
            "/api/v1/fixed-assets",
        )
        check_status(
            checks,
            "List fixed assets",
            request(
                "GET",
                f"/api/v1/fixed-assets?q={inv_number}&limit=50&offset=0",
                bearer=operator_token,
            ),
            200,
        )
        asset_get = request(
            "GET", f"/api/v1/fixed-assets/{asset_id}", bearer=operator_token
        )
        check_condition(
            checks,
            "Get fixed asset",
            _record_ok(asset_get, asset_id),
            "Created asset is returned"
            if _record_ok(asset_get, asset_id)
            else f"HTTP {asset_get.status}; expected created asset",
        )
        check_status(
            checks,
            "Update fixed asset",
            request(
                "PATCH",
                f"/api/v1/fixed-assets/{asset_id}",
                bearer=operator_token,
                payload={"owner": "Reference E2E"},
            ),
            200,
        )
        check_status(
            checks,
            "Duplicate inventory number returns 409",
            request(
                "POST",
                "/api/v1/fixed-assets",
                bearer=operator_token,
                payload={
                    "inv_number": inv_number,
                    "name": "Duplicate inventory test",
                    "asset_type": "diesel",
                },
            ),
            409,
        )
        check_status(
            checks,
            "Duplicate Wialon ID returns 409",
            request(
                "POST",
                "/api/v1/fixed-assets",
                bearer=operator_token,
                payload={
                    "inv_number": f"ASSET-OTHER-{suffix}",
                    "name": "Duplicate Wialon test",
                    "asset_type": "diesel",
                    "wialon_id": wialon_id,
                },
            ),
            409,
        )
        check_status(
            checks,
            "Fixed-asset statistics",
            request("GET", "/api/v1/fixed-assets/stats", bearer=operator_token),
            200,
        )
        check_status(
            checks,
            "Master sees own fixed asset",
            request("GET", f"/api/v1/fixed-assets/{asset_id}", bearer=master_token),
            200,
        )
        check_status(
            checks,
            "Master cannot see another section's asset",
            request(
                "GET", f"/api/v1/fixed-assets/{other_asset_id}", bearer=master_token
            ),
            404,
        )
        master_other_list = request(
            "GET",
            f"/api/v1/fixed-assets?section_id={other_section_id}&limit=1000",
            bearer=master_token,
        )
        master_items = parse_object(master_other_list).get("items", [])
        check_condition(
            checks,
            "Master section filter is enforced server-side",
            master_other_list.status == 200
            and isinstance(master_items, list)
            and all(item.get("section_id") == own_section_id for item in master_items),
            "No asset outside the master's section is returned"
            if master_other_list.status == 200
            and isinstance(master_items, list)
            and all(item.get("section_id") == own_section_id for item in master_items)
            else "Response included an asset outside the assigned section",
        )
        check_status(
            checks,
            "Master cannot create fixed assets",
            request(
                "POST",
                "/api/v1/fixed-assets",
                bearer=master_token,
                payload={
                    "inv_number": f"FORBIDDEN-{suffix}",
                    "name": "Forbidden asset",
                    "asset_type": "locomotive",
                },
            ),
            403,
        )

        manual_patch = request(
            "PATCH",
            f"/api/v1/fixed-assets/{asset_id}",
            bearer=operator_token,
            payload={"mileage": 111.25},
        )
        check_status(checks, "PATCH mileage", manual_patch, 200)
        manual_history = request(
            "GET",
            f"/api/v1/fixed-assets/{asset_id}/mileage-history?days=30&limit=100",
            bearer=operator_token,
        )
        _check_history(checks, "PATCH records manual mileage history", manual_history, "manual", "111.25")
        post_mileage = request(
            "POST",
            f"/api/v1/fixed-assets/{asset_id}/mileage",
            bearer=operator_token,
            payload={"mileage": 112.5},
        )
        check_status(checks, "POST mileage", post_mileage, 200)
        manual_history = request(
            "GET",
            f"/api/v1/fixed-assets/{asset_id}/mileage-history?days=30&limit=100",
            bearer=operator_token,
        )
        _check_history(checks, "POST records manual mileage history", manual_history, "manual", "112.5")

        check_status(
            checks,
            "Wialon request without token returns 401",
            request(
                "POST",
                "/api/v1/wialon/input",
                payload={"i": wialon_id, "mileage": 222.25},
            ),
            401,
        )
        wialon_query = urlencode(
            {"token": ingest_token, "i": wialon_id, "total_km": "222.25"}
        )
        wialon_by_id = request("GET", f"/api/v1/wialon/input?{wialon_query}")
        wialon_by_id_body = parse_object(wialon_by_id)
        check_condition(
            checks,
            "Wialon matches by wialon_id",
            wialon_by_id.status == 200
            and wialon_by_id_body.get("found") is True
            and wialon_by_id_body.get("asset_id") == asset_id,
            "Wialon unit ID resolves to the matching fixed asset"
            if wialon_by_id.status == 200
            and wialon_by_id_body.get("found") is True
            and wialon_by_id_body.get("asset_id") == asset_id
            else f"HTTP {wialon_by_id.status}; no matching asset returned",
        )
        _check_history(
            checks,
            "Wialon writes mileage history",
            request(
                "GET",
                f"/api/v1/fixed-assets/{asset_id}/mileage-history?days=30&limit=100",
                bearer=operator_token,
            ),
            "wialon",
            "222.25",
        )

        fallback_name = f"Reference Unit Number {number_suffix}"
        fallback_asset_response = request(
            "POST",
            "/api/v1/fixed-assets",
            bearer=operator_token,
            payload={
                "inv_number": f"ASSET-NUM-{suffix}",
                "name": fallback_name,
                "asset_type": "diesel",
                "section_id": own_section_id,
            },
        )
        fallback_asset_id = _record_created(
            checks,
            resources,
            "Create name-number match asset",
            fallback_asset_response,
            "/api/v1/fixed-assets",
        )
        wialon_by_number = request(
            "POST",
            "/api/v1/wialon/input",
            headers={"X-Ingest-Token": ingest_token},
            payload={
                "nm": f"Incoming Wialon Unit #{number_suffix}",
                "odo": "333.75",
            },
        )
        number_body = parse_object(wialon_by_number)
        check_condition(
            checks,
            "Wialon matches by number in unit name",
            wialon_by_number.status == 200
            and number_body.get("found") is True
            and number_body.get("asset_id") == fallback_asset_id,
            "Name number resolves to the matching locomotive/diesel asset"
            if wialon_by_number.status == 200
            and number_body.get("found") is True
            and number_body.get("asset_id") == fallback_asset_id
            else f"HTTP {wialon_by_number.status}; no matching asset returned",
        )
        check_condition(
            checks,
            "Wialon mileage is updated",
            str(number_body.get("mileage")) == "333.75",
            "Current mileage in the Wialon response is updated"
            if str(number_body.get("mileage")) == "333.75"
            else "Returned mileage did not match the incoming value",
        )

        unknown_query = urlencode(
            {
                "token": ingest_token,
                "nm": "No matching unregistered equipment",
                "mileage": "99",
            }
        )
        unknown = request("GET", f"/api/v1/wialon/input?{unknown_query}")
        check_condition(
            checks,
            "Wialon reports unknown unit",
            unknown.status == 200 and parse_object(unknown).get("found") is False,
            "Unknown Wialon unit is acknowledged without an asset match"
            if unknown.status == 200 and parse_object(unknown).get("found") is False
            else f"HTTP {unknown.status}; expected found=false",
        )

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
        print(f"\nAsset test stopped: {stopped_reason}")
    print_results(checks)
    return 1 if stopped_reason or any(not item.passed for item in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
