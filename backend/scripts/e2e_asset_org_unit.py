"""Verify bulk organizational-unit assignment against a disposable API."""

from __future__ import annotations

import getpass
import sys
from typing import Any

from e2e_smoke import (
    ApiSession,
    Check,
    SmokeError,
    check_condition,
    parse_object,
    print_results,
    request,
    require_status,
)


def _items(response: Any) -> list[dict[str, Any]]:
    items = parse_object(response).get("items")
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise SmokeError("API response did not contain a paginated item list")
    return items


def main() -> int:
    checks: list[Check] = []
    token: str | None = None
    asset_id: str | None = None
    original_org_unit_id: str | None = None
    stopped_reason: str | None = None
    email = getpass.getpass("Admin/operator email: ").strip()
    password = getpass.getpass("Password: ")
    if not email or not password:
        print("Credentials are required.")
        return 2

    try:
        login = request(
            "POST",
            "/api/v1/auth/login",
            payload={"email": email, "password": password},
            session=ApiSession(),
        )
        require_status(checks, "Login", login, 200)
        token = parse_object(login).get("access_token")
        if not isinstance(token, str) or not token:
            raise SmokeError("Login response did not contain an access token")

        assets_response = request(
            "GET",
            "/api/v1/fixed-assets?limit=1&offset=0",
            bearer=token,
        )
        require_status(checks, "Load one fixed asset", assets_response, 200)
        assets = _items(assets_response)
        if not assets or not isinstance(assets[0].get("id"), str):
            raise SmokeError("A fixed asset is required for the bulk assignment check")
        asset_id = assets[0]["id"]
        original_org_unit_id = assets[0].get("org_unit_id")

        sections_response = request(
            "GET",
            "/api/v1/sections?limit=1000&offset=0&is_active=true",
            bearer=token,
        )
        require_status(checks, "Load active sections", sections_response, 200)
        sections = _items(sections_response)
        target = next(
            (row for row in sections if isinstance(row.get("id"), str)),
            None,
        )
        if target is None:
            raise SmokeError("An active section is required for the bulk assignment check")

        update_response = request(
            "POST",
            "/api/v1/fixed-assets/bulk-org-unit",
            bearer=token,
            payload={"asset_ids": [asset_id], "org_unit_id": target["id"]},
        )
        require_status(checks, "Assign organizational unit", update_response, 200)
        check_condition(
            checks,
            "Bulk response reports the changed asset",
            parse_object(update_response).get("updated") == 1,
            "One asset was updated",
        )

        asset_response = request(
            "GET",
            f"/api/v1/fixed-assets/{asset_id}",
            bearer=token,
        )
        require_status(checks, "Verify organizational-unit assignment", asset_response, 200)
        check_condition(
            checks,
            "Passport reflects the selected unit",
            parse_object(asset_response).get("org_unit_id") == target["id"],
            "The asset has the selected organizational unit",
        )
    except SmokeError as exc:
        stopped_reason = str(exc)
    finally:
        if token is not None and asset_id is not None:
            restore_response = request(
                "POST",
                "/api/v1/fixed-assets/bulk-org-unit",
                bearer=token,
                payload={
                    "asset_ids": [asset_id],
                    "org_unit_id": original_org_unit_id,
                },
            )
            check_condition(
                checks,
                "Restore original organizational unit",
                restore_response.status == 200,
                f"HTTP {restore_response.status}",
            )

    if stopped_reason:
        print(f"Stopped: {stopped_reason}")
    print_results(checks)
    return 1 if stopped_reason or any(not item.passed for item in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
