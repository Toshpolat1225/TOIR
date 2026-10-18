"""Exercise fixed-asset catalog CRUD against the deployed API."""

from __future__ import annotations

import getpass
import secrets
import sys
import uuid
from typing import Any

from e2e_refs import _record_created
from e2e_smoke import (
    ApiSession, Check, SmokeError, check_condition, check_status,
    create_test_user, parse_object, print_results, request, require_status,
)


def main() -> int:
    checks: list[Check] = []
    resources: list[tuple[str, str]] = []
    admin_token: str | None = None
    operator_id: str | None = None
    stopped: str | None = None
    session = ApiSession()
    suffix = uuid.uuid4().hex[:12]
    email = getpass.getpass("Admin email: ").strip()
    password = getpass.getpass("Admin password: ")
    if not email or not password:
        print("Admin credentials are required.")
        return 2

    type_code, status_code = f"e2e_type_{suffix}", f"e2e_status_{suffix}"
    names_type = {"ru": f"E2E type {suffix}", "uz-Latn": f"E2E turi {suffix}", "uz-Cyrl": f"E2E тури {suffix}"}
    names_status = {"ru": f"E2E status {suffix}", "uz-Latn": f"E2E holat {suffix}", "uz-Cyrl": f"E2E ҳолат {suffix}"}
    try:
        login = request("POST", "/api/v1/auth/login", payload={"email": email, "password": password}, session=session)
        require_status(checks, "Admin login", login, 200)
        admin_token = parse_object(login).get("access_token")
        if not isinstance(admin_token, str) or not admin_token:
            raise SmokeError("Admin login did not return an access token")

        no_token = request("GET", "/api/v1/fixed-asset-catalogs/types?limit=1")
        check_status(checks, "Catalog requires authentication", no_token, 401)
        operator_response, operator_email, operator_password = create_test_user(admin_token, "asset-catalog")
        operator_id = _record_created(checks, [], "Create temporary operator", operator_response, "/api/v1/users")
        op_login = request("POST", "/api/v1/auth/login", payload={"email": operator_email, "password": operator_password}, session=ApiSession())
        require_status(checks, "Operator login", op_login, 200)
        operator_token = parse_object(op_login).get("access_token")
        if not isinstance(operator_token, str) or not operator_token:
            raise SmokeError("Operator login did not return an access token")

        denied = request("POST", "/api/v1/fixed-asset-catalogs/types", bearer=operator_token,
                         payload={"code": type_code, "names": names_type, "is_active": True, "color": "blue"})
        check_status(checks, "Operator cannot create catalog values", denied, 403)
        initial = request("GET", "/api/v1/fixed-asset-catalogs/types?q=e2e_missing_value_92d", bearer=admin_token)
        require_status(checks, "Empty search response", initial, 200)
        empty_items = parse_object(initial).get("items") == []
        check_condition(checks, "Empty catalog search returns an empty list", empty_items, "items is empty" if empty_items else "items was not empty")

        blank = request("POST", "/api/v1/fixed-asset-catalogs/types", bearer=admin_token,
                        payload={"code": type_code, "names": {"ru": " ", "uz-Latn": names_type["uz-Latn"], "uz-Cyrl": names_type["uz-Cyrl"]}, "is_active": True, "color": "blue"})
        check_status(checks, "Empty translated name is rejected", blank, 422)
        created_type = request("POST", "/api/v1/fixed-asset-catalogs/types", bearer=admin_token,
                               payload={"code": type_code, "names": names_type, "is_active": True, "color": "blue"})
        check_status(checks, "Create type", created_type, 201)
        resources.append(("/api/v1/fixed-asset-catalogs/types", type_code))
        duplicate = request("POST", "/api/v1/fixed-asset-catalogs/types", bearer=admin_token,
                            payload={"code": type_code, "names": names_type, "is_active": True, "color": "blue"})
        check_status(checks, "Duplicate code is rejected", duplicate, 409)
        duplicate_name = request("POST", "/api/v1/fixed-asset-catalogs/types", bearer=admin_token,
                                 payload={"code": f"e2e_other_{suffix}", "names": names_type, "is_active": True, "color": "blue"})
        check_status(checks, "Duplicate translated name is rejected", duplicate_name, 409)

        created_status = request("POST", "/api/v1/fixed-asset-catalogs/statuses", bearer=admin_token,
                                 payload={"code": status_code, "names": names_status, "is_active": True,
                                          "behavior": "maintenance", "color": "amber"})
        check_status(checks, "Create status", created_status, 201)
        resources.append(("/api/v1/fixed-asset-catalogs/statuses", status_code))
        asset = request("POST", "/api/v1/fixed-assets", bearer=admin_token,
                        payload={"inv_number": f"E2E-CATALOG-{suffix}", "name": "E2E catalog usage",
                                 "asset_type": type_code, "status": status_code, "mileage": 0})
        require_status(checks, "Create asset referencing test catalogs", asset, 201)
        asset_id = parse_object(asset).get("id")
        if not isinstance(asset_id, str):
            raise SmokeError("Created asset id missing")
        resources.append(("/api/v1/fixed-assets", asset_id))
        for kind, code in (("types", type_code), ("statuses", status_code)):
            blocked = request("DELETE", f"/api/v1/fixed-asset-catalogs/{kind}/{code}", bearer=admin_token)
            check_status(checks, f"Cannot delete used {kind}", blocked, 409)
            body = blocked.json()
            mentions_usage = "used by 1" in str(body.get("detail", ""))
            check_condition(checks, f"{kind} delete explains usage", mentions_usage, "Usage count appears in error" if mentions_usage else "Usage count missing")
            edit_payload: dict[str, Any] = {"names": names_type if kind == "types" else names_status,
                "is_active": False, "color": "gray"}
            if kind == "statuses":
                edit_payload["behavior"] = "maintenance"
            changed = request("PUT", f"/api/v1/fixed-asset-catalogs/{kind}/{code}", bearer=admin_token, payload=edit_payload)
            check_status(checks, f"Deactivate used {kind}", changed, 200)
        restore = request("DELETE", f"/api/v1/fixed-assets/{asset_id}", bearer=admin_token)
        check_status(checks, "Remove temporary asset", restore, 204)
        resources.remove(("/api/v1/fixed-assets", asset_id))
        for kind, code in (("statuses", status_code), ("types", type_code)):
            deleted = request("DELETE", f"/api/v1/fixed-asset-catalogs/{kind}/{code}", bearer=admin_token)
            check_status(checks, f"Delete unused {kind}", deleted, 204)
            resources.remove((f"/api/v1/fixed-asset-catalogs/{kind}", code))
    except SmokeError as exc:
        stopped = str(exc)
    finally:
        if admin_token:
            for endpoint, record_id in reversed(resources):
                response = request("DELETE", f"{endpoint}/{record_id}", bearer=admin_token)
                check_condition(checks, f"Cleanup {endpoint.rsplit('/', 1)[-1]}", response.status in {204, 404}, f"HTTP {response.status}")
            if operator_id:
                response = request("PATCH", f"/api/v1/users/{operator_id}", bearer=admin_token, payload={"is_active": False})
                check_status(checks, "Deactivate temporary operator", response, 200)
    if stopped:
        print(f"\nAsset catalog test stopped: {stopped}")
    print_results(checks)
    return 1 if stopped or any(not check.passed for check in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
