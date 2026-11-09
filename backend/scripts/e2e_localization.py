"""Verify Russian-only reference names against the intended TOIR API environment."""

from __future__ import annotations

import getpass
import sys
import uuid

from e2e_smoke import (
    ApiSession,
    Check,
    SmokeError,
    check_condition,
    check_status,
    parse_object,
    print_results,
    request,
)


def main() -> int:
    checks: list[Check] = []
    token: str | None = None
    section_id: str | None = None
    suffix = uuid.uuid4().hex[:12]
    source_name = f"RU-E2E-{suffix}"
    russian_name = f"RU-E2E-name-{suffix}"
    email = getpass.getpass("Admin email: ").strip()
    password = getpass.getpass("Admin password: ")
    if not email or not password:
        print("Admin credentials are required.")
        return 2

    try:
        login = request(
            "POST",
            "/api/v1/auth/login",
            payload={"email": email, "password": password},
            session=ApiSession(),
        )
        check_status(checks, "Admin login", login, 200)
        if login.status != 200:
            return _finish(checks)
        token_value = parse_object(login).get("access_token")
        if not isinstance(token_value, str) or not token_value:
            raise SmokeError("Admin login response did not include an access token")
        token = token_value

        check_status(
            checks,
            "Russian-name endpoint requires authentication",
            request("GET", "/api/v1/translations/section?limit=1"),
            401,
        )
        section = request(
            "POST",
            "/api/v1/sections",
            bearer=token,
            payload={
                "name": source_name,
                "unit_type": "section",
                "translations": {"ru": source_name},
            },
        )
        check_status(checks, "Create temporary Russian section", section, 201)
        if section.status != 201:
            return _finish(checks)
        section_id_value = parse_object(section).get("id")
        if not isinstance(section_id_value, str):
            raise SmokeError("Created section response did not include an id")
        section_id = section_id_value

        detail = request(
            "GET",
            f"/api/v1/translations/section/{section_id}",
            bearer=token,
        )
        detail_data = parse_object(detail) if detail.status == 200 else {}
        check_condition(
            checks,
            "Section has one Russian name",
            detail.status == 200
            and detail_data.get("translations") == {"ru": source_name}
            and detail_data.get("missing_locales") == [],
            f"HTTP {detail.status}; only the Russian value exists",
        )

        saved = request(
            "PUT",
            f"/api/v1/translations/section/{section_id}/ru",
            bearer=token,
            payload={"name": russian_name},
        )
        check_status(checks, "Update Russian section name", saved, 200)

        russian_read = request(
            "GET",
            f"/api/v1/sections/{section_id}",
            bearer=token,
            headers={"Accept-Language": "ru"},
        )
        non_russian_header_read = request(
            "GET",
            f"/api/v1/sections/{section_id}",
            bearer=token,
            headers={"Accept-Language": "uz-Latn"},
        )
        ru_data = parse_object(russian_read) if russian_read.status == 200 else {}
        other_data = (
            parse_object(non_russian_header_read)
            if non_russian_header_read.status == 200
            else {}
        )
        check_condition(
            checks,
            "API always returns the Russian name",
            russian_read.status == 200
            and non_russian_header_read.status == 200
            and ru_data.get("name") == russian_name
            and other_data.get("name") == russian_name
            and "localized_name" not in ru_data,
            "Both responses use the same Russian field",
        )
        rejected = request(
            "PUT",
            f"/api/v1/translations/section/{section_id}/uz-Latn",
            bearer=token,
            payload={"name": "unsupported"},
        )
        check_status(checks, "Reject non-Russian translation", rejected, 422)
    except SmokeError as exc:
        checks.append(Check("Russian-only localization flow", False, str(exc)))
    finally:
        if token and section_id:
            response = request(
                "DELETE", f"/api/v1/sections/{section_id}", bearer=token
            )
            check_status(checks, "Archive temporary section", response, 204)
    return _finish(checks)


def _finish(checks: list[Check]) -> int:
    print_results(checks)
    return 0 if all(item.passed for item in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
