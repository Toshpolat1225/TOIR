"""Check audit-log authorization, filters, details, and CSV export against a test API."""

from __future__ import annotations

import getpass
import secrets
import sys
import uuid
from urllib.parse import urlencode

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


def main() -> int:
    checks: list[Check] = []
    admin_token: str | None = None
    test_user_id: str | None = None
    test_email = f"audit-{uuid.uuid4().hex}@example.invalid"
    test_password = secrets.token_urlsafe(32)
    session = ApiSession()
    admin_email = getpass.getpass("Admin email: ").strip()
    admin_password = getpass.getpass("Admin password: ")
    test_name = f"Audit E2E {uuid.uuid4().hex[:12]}"

    try:
        login = request(
            "POST",
            "/api/v1/auth/login",
            payload={"email": admin_email, "password": admin_password},
            session=session,
        )
        require_status(checks, "Admin login", login, 200)
        admin_token = parse_object(login).get("access_token")
        if not isinstance(admin_token, str) or not admin_token:
            raise SmokeError("Admin login response did not include an access token")

        created = request(
            "POST",
            "/api/v1/users",
            bearer=admin_token,
            payload={
                "email": test_email,
                "full_name": test_name,
                "password": test_password,
                "role": "operator",
                "is_active": True,
            },
        )
        require_status(checks, "Create test user to produce an audit event", created, 201)
        test_user_id = str(parse_object(created)["id"])

        query = urlencode({"q": test_name, "action": "create", "limit": 10})
        events = request("GET", f"/api/v1/audit-logs?{query}", bearer=admin_token)
        require_status(checks, "Admin filters audit events", events, 200)
        event_rows = parse_object(events).get("items", [])
        matching = next(
            (
                row
                for row in event_rows
                if isinstance(row, dict)
                and row.get("object_label") == test_name
                and row.get("action") == "create"
            ),
            None,
        )
        check_condition(
            checks,
            "User creation has a searchable audit record",
            matching is not None,
            "A create event with the test object's name is present"
            if matching
            else "The matching event was not returned",
        )
        if matching is None:
            raise SmokeError("Missing user-creation audit event")

        detail = request(
            "GET",
            f"/api/v1/audit-logs/{matching['id']}",
            bearer=admin_token,
        )
        require_status(checks, "Admin opens event details", detail, 200)
        detail_data = parse_object(detail)
        check_condition(
            checks,
            "Event details include field changes",
            isinstance(detail_data.get("new_values"), dict)
            and detail_data["new_values"].get("full_name") == test_name,
            "The created user's new values are available",
        )

        facets = request("GET", "/api/v1/audit-logs/filters", bearer=admin_token)
        require_status(checks, "Admin loads filter choices", facets, 200)
        facet_data = parse_object(facets)
        check_condition(
            checks,
            "Filter choices include the users module",
            "users" in facet_data.get("modules", []),
            "The users module is available as a section filter",
        )

        export = request(
            "GET",
            f"/api/v1/audit-logs/export.csv?{urlencode({'q': test_name})}",
            bearer=admin_token,
        )
        check_condition(
            checks,
            "Filtered CSV export is returned",
            export.status == 200
            and export.headers.get("content-type", "").startswith("text/csv")
            and test_name.encode("utf-8") in export.body,
            f"HTTP {export.status}; content type {export.headers.get('content-type', 'missing')}",
        )

        require_status(
            checks,
            "Missing token cannot read audit logs",
            request("GET", "/api/v1/audit-logs"),
            401,
        )
        operator_login = request(
            "POST",
            "/api/v1/auth/login",
            payload={"email": test_email, "password": test_password},
        )
        require_status(checks, "Temporary operator login", operator_login, 200)
        operator_token = parse_object(operator_login).get("access_token")
        if not isinstance(operator_token, str) or not operator_token:
            raise SmokeError("Operator login response did not include an access token")
        check_status(
            checks,
            "Non-admin is forbidden from audit logs",
            request("GET", "/api/v1/audit-logs", bearer=operator_token),
            403,
        )
        require_status(
            checks,
            "Missing event returns 404",
            request(
                "GET",
                f"/api/v1/audit-logs/{uuid.uuid4()}",
                bearer=admin_token,
            ),
            404,
        )
    except (SmokeError, KeyError, TypeError, ValueError) as exc:
        checks.append(Check("E2E stopped", False, type(exc).__name__))
    finally:
        if admin_token and test_user_id:
            deactivated = request(
                "PATCH",
                f"/api/v1/users/{test_user_id}",
                bearer=admin_token,
                payload={"is_active": False},
            )
            check_status(checks, "Deactivate temporary test user", deactivated, 200)
    print_results(checks)
    return 1 if any(not item.passed for item in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
