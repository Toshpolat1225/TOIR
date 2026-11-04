"""Check generic unmatched-source API responses against a disposable test API."""

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


def main() -> int:
    checks: list[Check] = []
    email = getpass.getpass("Admin/operator email: ").strip()
    password = getpass.getpass("Password: ")
    if not email or not password:
        print("Credentials are required.")
        return 2
    stopped_reason: str | None = None
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
        for source in ("gtk", "wialon"):
            response = request(
                "GET",
                f"/api/v1/asset-links/unmatched?source={source}&limit=5&offset=0",
                bearer=token,
            )
            require_status(checks, f"{source} unmatched objects", response, 200)
            body: Any = parse_object(response)
            items = body.get("items")
            check_condition(
                checks,
                f"{source} unmatched response shape",
                isinstance(items, list)
                and isinstance(body.get("total"), int)
                and body.get("limit") == 5
                and body.get("offset") == 0
                and all(
                    isinstance(item, dict)
                    and item.get("source") == source
                    and item.get("level") in {"high", "ambiguous", "none"}
                    and "suggestion" in item
                    for item in items
                ),
                "Paginated mirror rows include suggestion levels",
            )
    except SmokeError as exc:
        stopped_reason = str(exc)
    if stopped_reason:
        print(f"Stopped: {stopped_reason}")
    print_results(checks)
    return 1 if stopped_reason or any(not item.passed for item in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
