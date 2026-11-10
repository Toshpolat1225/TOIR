"""Exercise fixed-asset, mileage, and Wialon endpoints against the API tunnel.

Run only after deploying the backend changes and configuring the API tunnel.
"""

from __future__ import annotations

import getpass
import os
import secrets
import sys
import uuid
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
                "number": f"1{number_suffix}",
                "depot": "ASSET TEST",
                "section_id": own_section_id,
                "status": "operational",
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
                "series": "TEST-WAGON",
                "number": f"2{number_suffix}",
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
                    "asset_type": "locomotive",
                    "series": "TEST",
                    "number": f"3{number_suffix}",
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
                    "asset_type": "locomotive",
                    "series": "TEST",
                    "number": f"4{number_suffix}",
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
        passport_report = request(
            "GET", "/api/v1/fixed-assets/passport-report", bearer=operator_token
        )
        require_status(checks, "Passport report JSON", passport_report, 200)
        passport_body = parse_object(passport_report)
        check_condition(
            checks,
            "Passport report JSON shape",
            all(
                isinstance(passport_body.get(key), list)
                for key in (
                    "depot_matches",
                    "depot_unmatched",
                    "duplicate_numbers",
                    "invalid_values",
                )
            ),
            "Report includes depot, duplicate, and invalid-value groups",
        )
        passport_csv = request(
            "GET",
            "/api/v1/fixed-assets/passport-report?format=csv",
            bearer=operator_token,
        )
        check_condition(
            checks,
            "Passport report CSV",
            passport_csv.status == 200
            and "text/csv" in passport_csv.headers.get("content-type", "")
            and passport_csv.body.startswith(b"category,asset_id,inv_number"),
            "CSV content type and header are present"
            if passport_csv.status == 200
            else f"HTTP {passport_csv.status}",
        )
        check_status(
            checks,
            "Master cannot read passport report",
            request(
                "GET",
                "/api/v1/fixed-assets/passport-report",
                bearer=master_token,
            ),
            403,
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
        check_status(checks, "PATCH cannot bypass opening approval", manual_patch, 422)
        post_mileage = request(
            "POST",
            f"/api/v1/fixed-assets/{asset_id}/mileage",
            bearer=operator_token,
            payload={"mileage": 112.5},
        )
        check_status(checks, "Legacy mileage endpoint is disabled", post_mileage, 422)

        opening_response = request(
            "POST",
            "/api/v1/wagon-mileage/openings",
            bearer=operator_token,
            payload={
                "asset_id": other_asset_id,
                "mileage_km": 50,
                "effective_at": datetime.now(timezone.utc).isoformat(),
                "note": "P0.3 E2E",
            },
        )
        opening_payload = parse_object(opening_response)
        opening_id = opening_payload.get("id")
        check_condition(
            checks,
            "Submit wagon opening balance",
            opening_response.status == 201
            and opening_payload.get("status") == "pending"
            and isinstance(opening_id, str),
            "Opening balance is pending approval"
            if opening_response.status == 201
            and opening_payload.get("status") == "pending"
            else f"HTTP {opening_response.status}",
        )
        if not isinstance(opening_id, str):
            raise SmokeError("Opening submission did not return an ID")
        opening_list = request(
            "GET",
            f"/api/v1/wagon-mileage/openings?asset_id={other_asset_id}&status=pending",
            bearer=operator_token,
        )
        opening_list_body = parse_object(opening_list)
        opening_items = opening_list_body.get("items")
        has_pending_opening = isinstance(opening_items, list) and any(
            isinstance(item, dict)
            and item.get("id") == opening_id
            and item.get("status") == "pending"
            for item in opening_items
        )
        check_condition(
            checks,
            "List wagon opening balances",
            opening_list.status == 200
            and opening_list_body.get("total") == 1
            and has_pending_opening,
            "Pending opening is visible"
            if opening_list.status == 200
            and opening_list_body.get("total") == 1
            else f"HTTP {opening_list.status}",
        )
        check_status(
            checks,
            "Master cannot read opening from another section",
            request(
                "GET",
                f"/api/v1/wagon-mileage/openings?asset_id={other_asset_id}",
                bearer=master_token,
            ),
            404,
        )
        approved_opening = request(
            "POST",
            f"/api/v1/wagon-mileage/openings/{opening_id}/approve",
            bearer=admin_token,
        )
        approved_payload = parse_object(approved_opening)
        check_condition(
            checks,
            "Admin approves opening balance",
            approved_opening.status == 200
            and approved_payload.get("status") == "approved"
            and approved_payload.get("approved_by") is not None
            and approved_payload.get("approved_at") is not None,
            "Approval audit is returned"
            if approved_opening.status == 200
            and approved_payload.get("status") == "approved"
            else f"HTTP {approved_opening.status}",
        )
        approved_asset = request(
            "GET",
            f"/api/v1/fixed-assets/{other_asset_id}",
            bearer=operator_token,
        )
        approved_asset_body = parse_object(approved_asset)
        check_condition(
            checks,
            "Approved opening does not auto-publish the mileage projection",
            approved_asset.status == 200
            and Decimal(str(approved_asset_body.get("mileage"))) == Decimal("0"),
            "Opening is approved without changing the existing projection"
            if approved_asset.status == 200
            and Decimal(str(approved_asset_body.get("mileage"))) == Decimal("0")
            else f"HTTP {approved_asset.status}; mileage projection changed",
        )

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
        reading_body = wialon_by_id_body.get("reading")
        reading_body = reading_body if isinstance(reading_body, dict) else {}
        check_condition(
            checks,
            "Wialon reading remains held and separate from asset mileage",
            reading_body.get("accepted") is True
            and reading_body.get("calculation_eligible") is False
            and reading_body.get("classification") == "HELD"
            and "mileage" not in wialon_by_id_body,
            "Reading is retained without returning fixed-asset mileage"
            if reading_body.get("classification") == "HELD"
            and "mileage" not in wialon_by_id_body
            else "Wialon reading was projected into fixed-asset mileage",
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
        wialon_without_link = request(
            "POST",
            "/api/v1/wialon/input",
            headers={"X-Ingest-Token": ingest_token},
            payload={
                "nm": f"Incoming Wialon Unit #{number_suffix}",
                "odo": "333.75",
            },
        )
        unlinked_body = parse_object(wialon_without_link)
        check_condition(
            checks,
            "Wialon name/number does not create an asset link",
            wialon_without_link.status == 200
            and unlinked_body.get("found") is False,
            "Name and number remain suggestions only"
            if wialon_without_link.status == 200
            and unlinked_body.get("found") is False
            else f"HTTP {wialon_without_link.status}; expected found=false",
        )
        fallback_wialon_id = f"manual-{suffix}"
        link_asset = request(
            "PATCH",
            f"/api/v1/fixed-assets/{fallback_asset_id}",
            bearer=operator_token,
            payload={"wialon_id": fallback_wialon_id},
        )
        check_status(checks, "PATCH assigns explicit Wialon ID", link_asset, 200)
        wialon_by_id = request(
            "POST",
            "/api/v1/wialon/input",
            headers={"X-Ingest-Token": ingest_token},
            payload={
                "i": fallback_wialon_id,
                "nm": f"Incoming Wialon Unit #{number_suffix}",
                "odo": "333.75",
            },
        )
        number_body = parse_object(wialon_by_id)
        check_condition(
            checks,
            "Wialon updates asset after explicit link",
            wialon_by_id.status == 200
            and number_body.get("found") is True
            and number_body.get("asset_id") == fallback_asset_id,
            "Exact wialon_id updates the selected fixed asset"
            if wialon_by_id.status == 200
            and number_body.get("found") is True
            and number_body.get("asset_id") == fallback_asset_id
            else f"HTTP {wialon_by_id.status}; no explicitly linked asset returned",
        )
        fallback_reading = number_body.get("reading")
        fallback_reading = fallback_reading if isinstance(fallback_reading, dict) else {}
        check_condition(
            checks,
            "Linked locomotive odometer is not projected into asset mileage",
            "mileage" not in number_body
            and fallback_reading.get("classification") == "HELD",
            "Wialon odometer remains separate and held"
            if "mileage" not in number_body
            else "Wialon odometer changed fixed-asset mileage",
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
