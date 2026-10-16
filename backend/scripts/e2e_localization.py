"""Exercise localization endpoints against the intended TOIR API environment."""

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
)


LOCALES = ("uz-Latn", "uz-Cyrl", "ru")


def _id(response: Any) -> str | None:
    value = parse_object(response).get("id")
    return value if isinstance(value, str) else None


def main() -> int:
    checks: list[Check] = []
    token: str | None = None
    department_id: str | None = None
    section_id: str | None = None
    translated_locales: list[str] = []
    suffix = uuid.uuid4().hex[:12]
    admin_email = getpass.getpass("Admin email: ").strip()
    admin_password = getpass.getpass("Admin password: ")
    if not admin_email or not admin_password:
        print("Admin email and password are required.")
        return 2

    try:
        login = request(
            "POST",
            "/api/v1/auth/login",
            payload={"email": admin_email, "password": admin_password},
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
            "Translations require authentication",
            request("GET", "/api/v1/translations/section?limit=1"),
            401,
        )

        department = request(
            "POST",
            "/api/v1/departments",
            bearer=token,
            payload={"name": f"L10N-{suffix}", "color": "#345678"},
        )
        check_status(checks, "Create temporary translation department", department, 201)
        if department.status != 201:
            return _finish(checks)
        department_id = _id(department)
        if department_id is None:
            raise SmokeError("Created department response did not include an id")

        section = request(
            "POST",
            "/api/v1/sections",
            bearer=token,
            payload={"name": f"L10N-{suffix}", "department_id": department_id},
        )
        check_status(checks, "Create temporary translation section", section, 201)
        if section.status != 201:
            return _finish(checks)
        section_id = _id(section)
        if section_id is None:
            raise SmokeError("Created section response did not include an id")

        before_translation = request(
            "GET",
            f"/api/v1/translations/section/{section_id}",
            bearer=token,
        )
        check_status(checks, "Read untranslated section fallback", before_translation, 200)
        before = parse_object(before_translation) if before_translation.status == 200 else {}
        check_condition(
            checks,
            "Missing translations are reported",
            len(before.get("missing_locales", [])) == len(LOCALES)
            and before.get("translations") == {},
            "all locale translations are initially missing",
        )
        fallback_list = request(
            "GET",
            f"/api/v1/sections/{section_id}",
            bearer=token,
            headers={"Accept-Language": "uz-Latn"},
        )
        check_status(checks, "GET section fallback", fallback_list, 200)
        fallback_row = parse_object(fallback_list) if fallback_list.status == 200 else None
        check_condition(
            checks,
            "Canonical label is the visible fallback",
            isinstance(fallback_row, dict)
            and fallback_row.get("localized_name") == f"L10N-{suffix}"
            and fallback_row.get("translation_missing") is True,
            "missing locale uses the canonical section name",
        )

        for locale in LOCALES:
            translated_name = f"{locale}-{suffix}"
            saved = request(
                "PUT",
                f"/api/v1/translations/section/{section_id}/{locale}",
                bearer=token,
                payload={"name": translated_name},
            )
            check_status(checks, f"Save {locale} translation", saved, 200)
            if saved.status != 200:
                continue
            translated_locales.append(locale)
            listed = request(
                "GET",
                f"/api/v1/sections/{section_id}",
                bearer=token,
                headers={"Accept-Language": locale},
            )
            check_status(checks, f"GET sections in {locale}", listed, 200)
            match = parse_object(listed) if listed.status == 200 else None
            check_condition(
                checks,
                f"Localized section label in {locale}",
                isinstance(match, dict) and match.get("localized_name") == translated_name,
                "localized_name matches the saved translation",
            )

        invalid_locale = request(
            "PUT",
            f"/api/v1/translations/section/{section_id}/xx",
            bearer=token,
            payload={"name": "invalid"},
        )
        check_status(checks, "Reject unsupported locale", invalid_locale, 422)
    except SmokeError as exc:
        checks.append(Check("Localization E2E flow", False, str(exc)))
    finally:
        if token and section_id:
            for locale in reversed(translated_locales):
                response = request(
                    "DELETE",
                    f"/api/v1/translations/section/{section_id}/{locale}",
                    bearer=token,
                )
                check_status(checks, f"Remove temporary {locale} translation", response, 204)
            response = request(
                "DELETE", f"/api/v1/sections/{section_id}", bearer=token
            )
            check_status(checks, "Remove temporary section", response, 204)
        if token and department_id:
            response = request(
                "DELETE", f"/api/v1/departments/{department_id}", bearer=token
            )
            check_status(checks, "Remove temporary department", response, 204)
    return _finish(checks)


def _finish(checks: list[Check]) -> int:
    print_results(checks)
    return 0 if all(item.passed for item in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
