"""Exercise GTK-generated conflicts against a disposable API with GTK configured."""

from __future__ import annotations

import getpass
import sys
import uuid
from typing import Any

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


def _items(response: Any) -> list[dict[str, Any]]:
    payload = parse_object(response)
    items = payload.get("items")
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise SmokeError("API response did not contain a paginated item list")
    return items


def main() -> int:
    checks: list[Check] = []
    created_assets: list[str] = []
    token: str | None = None
    stopped_reason: str | None = None
    email = getpass.getpass("Admin/operator email: ").strip()
    password = getpass.getpass("Password: ")
    if not email or not password:
        print("Credentials are required.")
        return 2

    suffix = uuid.uuid4().hex[:12]
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

        carriage_response = request(
            "GET",
            "/api/v1/gtk/carriages?is_active=true&duplicate=false&limit=1000",
            bearer=token,
        )
        require_status(checks, "Load GTK carriages", carriage_response, 200)
        carriages = [
            item
            for item in _items(carriage_response)
            if item.get("linked_asset") is None
            and isinstance(item.get("gtk_id"), int)
            and isinstance(item.get("reg_number"), str)
            and item["reg_number"].strip()
        ][:2]
        if len(carriages) != 2:
            raise SmokeError("Two active unlinked GTK carriages with registration numbers are required")

        links = []
        for index, carriage in enumerate(carriages):
            number = f"E2E-{suffix}-{index}"
            asset_response = request(
                "POST",
                "/api/v1/fixed-assets",
                bearer=token,
                payload={
                    "inv_number": f"CONFLICT-E2E-{suffix}-{index}",
                    "name": f"Conflict E2E {suffix} {index}",
                    "asset_type": "wagon",
                    "series": f"CONFLICT-E2E-{suffix}-{index}",
                    "number": number,
                    "status": "operational",
                    "mileage": 0,
                },
            )
            require_status(checks, f"Create temporary asset {index + 1}", asset_response, 201)
            asset_id = parse_object(asset_response).get("id")
            if not isinstance(asset_id, str):
                raise SmokeError("Created asset response did not contain an ID")
            created_assets.append(asset_id)
            links.append(
                {"asset_id": asset_id, "gtk_id": carriage["gtk_id"], "kind": "carriage"}
            )

        link_response = request(
            "POST", "/api/v1/gtk/links", bearer=token, payload={"links": links}
        )
        require_status(checks, "Link temporary assets to GTK", link_response, 200)
        sync_response = request("POST", "/api/v1/gtk/sync", bearer=token)
        require_status(checks, "Run GTK synchronization", sync_response, 200)
        sync_body = parse_object(sync_response)
        check_condition(
            checks,
            "GTK synchronization retained a complete snapshot",
            sync_body.get("status") == "ok",
            f"Returned status: {sync_body.get('status')}",
        )

        conflicts_response = request(
            "GET",
            "/api/v1/asset-conflicts?status=pending&limit=1000&offset=0",
            bearer=token,
        )
        require_status(checks, "List pending asset conflicts", conflicts_response, 200)
        conflict_rows = _items(conflicts_response)
        by_asset = {
            asset_id: next(
                (
                    row
                    for row in conflict_rows
                    if row.get("asset_id") == asset_id and row.get("field") == "number"
                ),
                None,
            )
            for asset_id in created_assets
        }
        check_condition(
            checks,
            "GTK proposes registration numbers without overwriting passport values",
            all(
                row is not None
                and row.get("status") == "pending"
                and row.get("kind") == "conflict"
                for row in by_asset.values()
            ),
            "Both linked assets have pending number conflicts",
        )
        if all(by_asset.values()):
            for index, action in enumerate(("reject", "accept")):
                row = by_asset[created_assets[index]]
                response = request(
                    "POST",
                    f"/api/v1/asset-conflicts/{row['id']}/{action}",
                    bearer=token,
                )
                require_status(checks, f"Resolve conflict with {action}", response, 200)
                expected_status = "rejected" if action == "reject" else "accepted"
                check_condition(
                    checks,
                    f"Conflict status becomes {expected_status}",
                    parse_object(response).get("status") == expected_status,
                    f"Expected status {expected_status}",
                )
    except SmokeError as exc:
        stopped_reason = str(exc)
    finally:
        if token is not None:
            for asset_id in reversed(created_assets):
                response = request(
                    "DELETE",
                    f"/api/v1/fixed-assets/{asset_id}",
                    bearer=token,
                )
                check_condition(
                    checks,
                    "Cleanup: delete temporary fixed asset",
                    response.status in {204, 404},
                    f"HTTP {response.status}",
                )

    if stopped_reason:
        print(f"Stopped: {stopped_reason}")
    print_results(checks)
    return 1 if stopped_reason or any(not item.passed for item in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
