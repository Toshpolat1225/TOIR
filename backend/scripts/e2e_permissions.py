"""E2E checks for database-backed permissions. Run only against a test API."""

from __future__ import annotations

import getpass
import secrets
import sys
import uuid
from e2e_smoke import ApiResponse, ApiSession, SmokeError, parse_object, request


def expect(label: str, response: ApiResponse, expected: int, results: list[str]) -> None:
    ok = response.status == expected
    results.append(f"{'PASS' if ok else 'FAIL'} {label}: HTTP {response.status}, kutilgan {expected}")
    if not ok:
        raise SmokeError(label)


def main() -> int:
    results: list[str] = []
    created_users: list[str] = []
    admin_token: str | None = None
    original_operator: list[str] | None = None
    admin_email = getpass.getpass("Admin email: ").strip()
    admin_password = getpass.getpass("Admin password: ")
    session = ApiSession()
    try:
        login = request("POST", "/api/v1/auth/login", payload={"email": admin_email, "password": admin_password}, session=session)
        expect("Admin login", login, 200, results)
        admin_token = str(parse_object(login)["access_token"])
        expect("Authenticated user reads own permissions", request("GET", "/api/v1/permissions/me", bearer=admin_token), 200, results)
        me = parse_object(request("GET", "/api/v1/auth/me", bearer=admin_token))
        users = request("GET", "/api/v1/users?limit=1000", bearer=admin_token, headers={"Accept": "application/json"})
        expect("Admin can read users", users, 200, results)
        rows = parse_object(users).get("items", [])
        active_admins = [row for row in rows if row.get("role") == "admin" and row.get("is_active")]
        if len(active_admins) == 1:
            expect("Last active admin is protected", request("PATCH", f"/api/v1/users/{me['id']}", bearer=admin_token, payload={"is_active": False}), 409, results)
        else:
            results.append("NOT TESTED Last-admin safeguard: test API has multiple active admins")

        no_token = request("GET", "/api/v1/dashboard/summary")
        expect("Missing token denied", no_token, 401, results)
        forbidden_manager = request("PUT", "/api/v1/permissions/management", payload={"granted": []})
        expect("Permission endpoint requires auth", forbidden_manager, 401, results)

        protected_admin_role = request("PUT", "/api/v1/permissions/admin", bearer=admin_token, payload={"granted": []})
        expect("Admin role permission set is immutable", protected_admin_role, 403, results)
        operator_matrix = request("GET", "/api/v1/permissions/operator", bearer=admin_token)
        expect("Admin reads operator permission matrix", operator_matrix, 200, results)
        original_operator = [item["code"] for item in parse_object(operator_matrix)["permissions"] if item["granted"]]
        elevated = request("PUT", "/api/v1/permissions/operator", bearer=admin_token, payload={"granted": original_operator + ["users.manage_users"]})
        expect("Delegated role cannot receive protected user management", elevated, 403, results)
        admin_create = request("POST", "/api/v1/users", bearer=admin_token, payload={"email": f"blocked-{uuid.uuid4().hex}@example.invalid", "full_name": "Blocked Admin", "password": secrets.token_urlsafe(32), "role": "admin", "is_active": True})
        expect("Admin role cannot be assigned through user API", admin_create, 403, results)

        email = f"rbac-{uuid.uuid4().hex}@example.invalid"
        password = secrets.token_urlsafe(32)
        created = request("POST", "/api/v1/users", bearer=admin_token, payload={"email": email, "full_name": "RBAC E2E", "password": password, "role": "operator", "is_active": True})
        expect("Create temporary operator", created, 201, results)
        created_users.append(str(parse_object(created)["id"]))

        check_login = request("POST", "/api/v1/auth/login", payload={"email": email, "password": password})
        expect("Temporary operator login before permission change", check_login, 200, results)
        user_token = str(parse_object(check_login)["access_token"])
        expect("Operator reads own permission list", request("GET", "/api/v1/permissions/me", bearer=user_token), 200, results)

        changed = [code for code in original_operator if code != "dashboard.view"]
        updated = request("PUT", "/api/v1/permissions/operator", bearer=admin_token, payload={"granted": changed})
        expect("Permission change saved", updated, 200, results)
        expect("Permission change applies to a current access token", request("GET", "/api/v1/dashboard/summary", bearer=user_token), 403, results)
        expect("No-token API remains unauthorized", request("GET", "/api/v1/permissions/operator"), 401, results)

        bad_permission = request("PUT", "/api/v1/permissions/operator", bearer=admin_token, payload={"granted": ["unknown.root"]})
        expect("Unknown permission rejected", bad_permission, 422, results)
        denied_manager = request("GET", "/api/v1/permissions/operator", bearer=user_token)
        expect("Non-admin cannot manage permission matrices", denied_manager, 403, results)

        section_response = request("GET", "/api/v1/sections?limit=100", bearer=admin_token)
        expect("Admin reads sections for scope check", section_response, 200, results)
        sections = parse_object(section_response).get("items", [])
        if len(sections) >= 2:
            assigned, foreign = sections[0]["id"], sections[1]["id"]
            master_email = f"rbac-master-{uuid.uuid4().hex}@example.invalid"
            master_password = secrets.token_urlsafe(32)
            master = request("POST", "/api/v1/users", bearer=admin_token, payload={"email": master_email, "full_name": "RBAC Master E2E", "password": master_password, "role": "master", "section_id": assigned, "is_active": True})
            expect("Create temporary scoped master", master, 201, results)
            created_users.append(str(parse_object(master)["id"]))
            master_login = request("POST", "/api/v1/auth/login", payload={"email": master_email, "password": master_password})
            expect("Temporary master login", master_login, 200, results)
            master_token = str(parse_object(master_login)["access_token"])
            asset_page = request("GET", f"/api/v1/fixed-assets?section_id={foreign}&limit=100", bearer=master_token)
            expect("Master asset list is scoped", asset_page, 200, results)
            assets = parse_object(asset_page)
            in_scope = all(item.get("section_id") == assigned for item in assets.get("items", []))
            results.append(f"{'PASS' if in_scope else 'FAIL'} Master cannot list other section assets")
            if not in_scope:
                raise SmokeError("Master section scope")
            expect("Master cannot read another section", request("GET", f"/api/v1/sections/{foreign}", bearer=master_token), 404, results)
        else:
            results.append("NOT TESTED Master cross-section scope: test API needs two sections")
    except (SmokeError, KeyError, TypeError, ValueError) as exc:
        results.append(f"STOPPED E2E check: {type(exc).__name__}")
    finally:
        if admin_token and original_operator is not None:
            restore = request("PUT", "/api/v1/permissions/operator", bearer=admin_token, payload={"granted": original_operator})
            results.append(f"{'PASS' if restore.status == 200 else 'FAIL'} Restore original operator permissions")
        if admin_token:
            for user_id in created_users:
                cleaned = request("PATCH", f"/api/v1/users/{user_id}", bearer=admin_token, payload={"is_active": False})
                results.append(f"{'PASS' if cleaned.status == 200 else 'FAIL'} Deactivate temporary user")
    print("\n".join(results))
    return 1 if any(line.startswith("FAIL") or line.startswith("STOPPED") for line in results) else 0


if __name__ == "__main__":
    sys.exit(main())
