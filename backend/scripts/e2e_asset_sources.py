"""Exercise passport model listing and source-link history on a disposable API."""

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
    asset_id: str | None = None
    token: str | None = None
    stopped_reason: str | None = None
    email = getpass.getpass("Admin/operator email: ").strip()
    password = getpass.getpass("Password: ")
    if not email or not password:
        print("Credentials are required.")
        return 2

    suffix = uuid.uuid4().hex
    external_id = f"VESAVOY-E2E-{suffix}"
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

        models_response = request(
            "GET",
            "/api/v1/fixed-assets/models?asset_type=wagon&limit=1000&offset=0",
            bearer=token,
        )
        require_status(checks, "List passport models", models_response, 200)
        model_payload = parse_object(models_response)
        model_items = _items(models_response)
        check_condition(
            checks,
            "Model list uses the paginated schema",
            isinstance(model_payload.get("total"), int)
            and isinstance(model_payload.get("limit"), int)
            and isinstance(model_payload.get("offset"), int)
            and all(
                {"id", "name", "name_normalized", "asset_type", "series"} <= item.keys()
                for item in model_items
            ),
            "Response includes pagination and asset model fields",
        )

        asset_response = request(
            "POST",
            "/api/v1/fixed-assets",
            bearer=token,
            payload={
                "inv_number": f"ASSET-SOURCE-E2E-{suffix}",
                "name": f"Asset source E2E {suffix}",
                "asset_type": "wagon",
                "series": f"Asset source model {suffix}",
                "number": suffix[:8],
                "status": "operational",
                "mileage": 0,
            },
        )
        require_status(checks, "Create temporary asset", asset_response, 201)
        asset_id = parse_object(asset_response).get("id")
        if not isinstance(asset_id, str):
            raise SmokeError("Created asset response did not contain an ID")

        link_response = request(
            "POST",
            f"/api/v1/fixed-assets/{asset_id}/links",
            bearer=token,
            payload={
                "source": "vesavoy",
                "external_id": external_id,
                "external_name": "E2E source",
            },
        )
        require_status(checks, "Create source link", link_response, 201)
        check_condition(
            checks,
            "Created source link is active",
            parse_object(link_response).get("status") == "active",
            "Link status is active",
        )

        history_response = request(
            "GET",
            f"/api/v1/fixed-assets/{asset_id}/links?include_ended=true",
            bearer=token,
        )
        require_status(checks, "Load source-link history", history_response, 200)
        history = _items(history_response)
        check_condition(
            checks,
            "History includes the active link",
            any(item.get("external_id") == external_id and item.get("status") == "active" for item in history),
            "The newly created link appears in history",
        )

        unlink_response = request(
            "DELETE",
            f"/api/v1/fixed-assets/{asset_id}/links/vesavoy",
            bearer=token,
        )
        require_status(checks, "End source link", unlink_response, 200)
        check_condition(
            checks,
            "Unlink preserves an ended history row",
            parse_object(unlink_response).get("status") == "ended",
            "Unlinked row status is ended",
        )

        ended_response = request(
            "GET",
            f"/api/v1/fixed-assets/{asset_id}/links?include_ended=true",
            bearer=token,
        )
        require_status(checks, "Reload ended source-link history", ended_response, 200)
        check_condition(
            checks,
            "Ended link remains in history",
            any(item.get("external_id") == external_id and item.get("status") == "ended" for item in _items(ended_response)),
            "The ended link is retained",
        )
    except SmokeError as exc:
        stopped_reason = str(exc)
    finally:
        if token is not None and asset_id is not None:
            response = request(
                "DELETE",
                f"/api/v1/fixed-assets/{asset_id}",
                bearer=token,
            )
            check_condition(
                checks,
                "Cleanup: delete temporary asset",
                response.status in {204, 404},
                f"HTTP {response.status}",
            )

    if stopped_reason:
        print(f"Stopped: {stopped_reason}")
    print_results(checks)
    return 1 if stopped_reason or any(not item.passed for item in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
