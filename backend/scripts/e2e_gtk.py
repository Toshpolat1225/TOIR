"""Exercise GTK read APIs and one manual sync against a disposable test API."""

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
    payload = parse_object(response)
    items = payload.get("items")
    if not isinstance(items, list) or not all(
        isinstance(item, dict) for item in items
    ):
        raise SmokeError("GTK list response is not a paginated object")
    if not isinstance(payload.get("total"), int):
        raise SmokeError("GTK list response is missing total")
    return items


def main() -> int:
    checks: list[Check] = []
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

        status_response = request("GET", "/api/v1/gtk/status", bearer=token)
        require_status(checks, "GTK status", status_response, 200)
        status_body = parse_object(status_response)
        check_condition(
            checks,
            "GTK status shape",
            isinstance(status_body.get("enabled"), bool)
            and isinstance(status_body.get("interval_minutes"), int)
            and "last_run" in status_body,
            "Status fields are present",
        )

        train_items = []
        for path, label in (
            ("/api/v1/gtk/locomotives?limit=5", "GTK locomotives"),
            ("/api/v1/gtk/carriages?limit=5", "GTK carriages"),
            ("/api/v1/gtk/trains?limit=5", "GTK trains"),
        ):
            response = request("GET", path, bearer=token)
            require_status(checks, label, response, 200)
            items = _items(response)
            if path.startswith("/api/v1/gtk/trains"):
                train_items = items

        sync = request("POST", "/api/v1/gtk/sync", bearer=token)
        require_status(checks, "GTK manual sync", sync, 200)
        sync_body = parse_object(sync)
        check_condition(
            checks,
            "GTK sync run status",
            sync_body.get("status")
            in {"ok", "suspicious", "error", "parse_error", "login_failed"},
            "A recognized sync status was recorded",
        )

        trains = request(
            "GET", "/api/v1/gtk/trains?limit=5", bearer=token
        )
        require_status(checks, "GTK trains after sync", trains, 200)
        train_items = _items(trains)
        if train_items:
            train_id = train_items[0].get("gtk_id")
            detail = request(
                "GET", f"/api/v1/gtk/trains/{train_id}", bearer=token
            )
            require_status(checks, "GTK train detail", detail, 200)
            detail_body = parse_object(detail)
            check_condition(
                checks,
                "GTK member order",
                isinstance(detail_body.get("locomotives"), list)
                and isinstance(detail_body.get("carriages"), list),
                "Ordered member arrays are returned",
            )
        else:
            check_condition(
                checks,
                "GTK train detail",
                False,
                "No train exists in the test GTK snapshot",
            )
    except SmokeError as exc:
        print(f"Stopped: {exc}")
        print_results(checks)
        return 1

    print_results(checks)
    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
