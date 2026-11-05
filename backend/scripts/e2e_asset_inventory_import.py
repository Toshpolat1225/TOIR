"""Verify inventory-import preview and safe rejection against a disposable API."""

from __future__ import annotations

import getpass
import sys
from uuid import uuid4

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

        preview = request(
            "POST",
            "/api/v1/fixed-assets/inv-import/preview",
            bearer=token,
            payload={"rows": [{"asset_id": "", "inv_number": ""}]},
        )
        require_status(checks, "Preview an empty row", preview, 200)
        items = parse_object(preview).get("items")
        check_condition(
            checks,
            "Preview marks the row empty",
            isinstance(items, list)
            and len(items) == 1
            and items[0].get("status") == "empty",
            "No data was written",
        )

        apply = request(
            "POST",
            "/api/v1/fixed-assets/inv-import/apply",
            bearer=token,
            payload={
                "rows": [
                    {
                        "asset_id": str(uuid4()),
                        "inv_number": f"P7-NOT-FOUND-{uuid4().hex}",
                    }
                ]
            },
        )
        check_condition(
            checks,
            "Apply rejects an asset missing after preview",
            apply.status == 409,
            f"HTTP {apply.status}; no fixed asset should be changed",
        )
    except SmokeError as exc:
        print(f"Stopped: {exc}")

    print_results(checks)
    return 1 if any(not item.passed for item in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
