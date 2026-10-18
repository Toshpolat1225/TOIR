"""Check user activation, login denial, token invalidation and status permissions."""

from __future__ import annotations

import getpass
import secrets
import sys
import uuid
from urllib.parse import urlencode

from e2e_smoke import ApiSession, SmokeError, parse_object, request


def expect(label: str, response, expected: int, results: list[str]) -> None:
    ok = response.status == expected
    results.append(f"{'PASS' if ok else 'FAIL'} {label}: HTTP {response.status}, kutilgan {expected}")
    if not ok:
        raise SmokeError(label)


def main() -> int:
    results: list[str] = []
    admin_token: str | None = None
    user_id: str | None = None
    admin_email = getpass.getpass("Admin email: ").strip()
    admin_password = getpass.getpass("Admin password: ")
    admin_session = ApiSession()
    user_session = ApiSession()
    try:
        login = request("POST", "/api/v1/auth/login", payload={"email": admin_email, "password": admin_password}, session=admin_session)
        expect("Admin login", login, 200, results)
        admin_token = str(parse_object(login)["access_token"])
        admin = parse_object(request("GET", "/api/v1/auth/me", bearer=admin_token))
        self_deactivate = request("PATCH", f"/api/v1/users/{admin['id']}", bearer=admin_token, payload={"is_active": False})
        expect("Admin cannot deactivate self", self_deactivate, 409, results)
        expect("Unauthenticated status change denied", request("PATCH", f"/api/v1/users/{admin['id']}", payload={"is_active": False}), 401, results)
        admin_list = request("GET", "/api/v1/users?limit=1000", bearer=admin_token)
        expect("Admin list available for last-admin check", admin_list, 200, results)
        filtered_admin_list = request(
            "GET", f"/api/v1/users?{urlencode({'q': admin_email, 'is_active': 'true', 'limit': 1000})}", bearer=admin_token
        )
        expect("User email and active filters", filtered_admin_list, 200, results)
        if not any(item.get("id") == admin.get("id") for item in parse_object(filtered_admin_list).get("items", [])):
            raise SmokeError("Active user search did not return the matching admin")
        results.append("PASS Active user search returns the matching record")
        active_admins = [item for item in parse_object(admin_list).get("items", []) if item.get("role") == "admin" and item.get("is_active")]
        if len(active_admins) == 1:
            expect("Last active admin cannot be deactivated", request("PATCH", f"/api/v1/users/{admin['id']}", bearer=admin_token, payload={"is_active": False}), 409, results)
        else:
            results.append("NOT TESTED Last-admin safeguard: API has multiple active admins")

        email = f"user-status-{uuid.uuid4().hex}@example.invalid"
        password = secrets.token_urlsafe(32)
        created = request("POST", "/api/v1/users", bearer=admin_token, payload={"email": email, "full_name": "User Status E2E", "password": password, "role": "operator", "is_active": True})
        expect("Create temporary active user", created, 201, results)
        user_id = str(parse_object(created)["id"])
        active_login = request("POST", "/api/v1/auth/login", payload={"email": email, "password": password}, session=user_session)
        expect("Active user can login", active_login, 200, results)
        old_access = str(parse_object(active_login)["access_token"])

        denied_user_change = request("PATCH", f"/api/v1/users/{user_id}", bearer=old_access, payload={"is_active": False})
        expect("Non-admin cannot change active status", denied_user_change, 403, results)
        deactivated = request("PATCH", f"/api/v1/users/{user_id}", bearer=admin_token, payload={"is_active": False})
        expect("Admin deactivates user", deactivated, 200, results)
        expect("Old access token is rejected", request("GET", "/api/v1/auth/me", bearer=old_access), 401, results)
        expect("Old refresh session is rejected", request("POST", "/api/v1/auth/refresh", session=user_session), 401, results)
        expect("Inactive user cannot login", request("POST", "/api/v1/auth/login", payload={"email": email, "password": password}), 401, results)

        users = request("GET", "/api/v1/users?limit=1000", bearer=admin_token)
        expect("Admin list remains available", users, 200, results)
        persisted = any(str(item.get("id")) == user_id and item.get("is_active") is False for item in parse_object(users).get("items", []))
        results.append(f"{'PASS' if persisted else 'FAIL'} Inactive account and historical identity remain in user list")
        if not persisted:
            raise SmokeError("Inactive user persistence")

        activated = request("PATCH", f"/api/v1/users/{user_id}", bearer=admin_token, payload={"is_active": True})
        expect("Admin reactivates user", activated, 200, results)
        expect("Reactivated user can login", request("POST", "/api/v1/auth/login", payload={"email": email, "password": password}), 200, results)
    except (SmokeError, KeyError, TypeError, ValueError) as exc:
        results.append(f"STOPPED E2E check: {type(exc).__name__}")
    finally:
        if admin_token and user_id:
            cleanup = request("PATCH", f"/api/v1/users/{user_id}", bearer=admin_token, payload={"is_active": False})
            results.append(f"{'PASS' if cleanup.status == 200 else 'FAIL'} Leave temporary account inactive (user delete API is not available)")
    print("\n".join(results))
    return 1 if any(line.startswith("FAIL") or line.startswith("STOPPED") for line in results) else 0


if __name__ == "__main__":
    sys.exit(main())
