"""Run authentication and authorization smoke checks against the API tunnel."""

from __future__ import annotations

import getpass
import json
import os
import secrets
import sys
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


BASE_URL = os.environ.get("TOIR_API_BASE_URL", "http://localhost:8010").rstrip("/")
FOREIGN_ORIGIN = "https://smoke-foreign.example.invalid"
TIMEOUT_SECONDS = 15


class SmokeError(Exception):
    """An expected failure while running the smoke checks."""


@dataclass(frozen=True)
class ApiResponse:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise SmokeError("API returned an invalid JSON response") from exc


@dataclass
class Check:
    label: str
    passed: bool
    result: str


@dataclass
class TestUser:
    user_id: str
    email: str
    password: str
    inactive: bool = False


def request(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    bearer: str | None = None,
    headers: dict[str, str] | None = None,
) -> ApiResponse:
    request_headers = dict(headers or {})
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    if bearer is not None:
        request_headers["Authorization"] = f"Bearer {bearer}"

    http_request = Request(
        f"{BASE_URL}{path}",
        data=body,
        headers=request_headers,
        method=method,
    )
    try:
        with urlopen(http_request, timeout=TIMEOUT_SECONDS) as response:
            return ApiResponse(
                response.status,
                {name.lower(): value for name, value in response.headers.items()},
                response.read(),
            )
    except HTTPError as response:
        response.close()
        return ApiResponse(
            response.code,
            {name.lower(): value for name, value in response.headers.items()},
            b"",
        )
    except (URLError, TimeoutError, OSError) as exc:
        raise SmokeError("API request failed; verify that the tunnel is available") from exc


def check_status(checks: list[Check], label: str, response: ApiResponse, expected: int) -> bool:
    passed = response.status == expected
    checks.append(
        Check(
            label,
            passed,
            f"HTTP {response.status} (expected {expected})",
        )
    )
    return passed


def check_condition(
    checks: list[Check], label: str, passed: bool, result: str
) -> bool:
    checks.append(Check(label, passed, result))
    return passed


def require_status(
    checks: list[Check], label: str, response: ApiResponse, expected: int
) -> None:
    if not check_status(checks, label, response, expected):
        raise SmokeError(f"Cannot continue: {label}")


def parse_object(response: ApiResponse) -> dict[str, Any]:
    parsed = response.json()
    if not isinstance(parsed, dict):
        raise SmokeError("API returned an unexpected response shape")
    return parsed


def required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise SmokeError("API response is missing a required field")
    return value


def create_test_user(admin_token: str, suffix: str) -> tuple[ApiResponse, str, str]:
    email = f"smoke-{uuid.uuid4().hex}@example.invalid"
    password = secrets.token_urlsafe(32)
    response = request(
        "POST",
        "/api/v1/users",
        bearer=admin_token,
        payload={
            "email": email,
            "full_name": f"Smoke test {suffix}",
            "password": password,
            "role": "operator",
            "is_active": True,
        },
    )
    return response, email, password


def print_results(checks: list[Check]) -> None:
    print("\nTekshiruv -> natija")
    print("| Tekshiruv | Natija | Izoh |")
    print("|---|---|---|")
    for item in checks:
        result = "o'tdi" if item.passed else "yiqildi"
        print(f"| {item.label} | {result} | {item.result} |")


def main() -> int:
    checks: list[Check] = []
    users: list[TestUser] = []
    admin_access: str | None = None
    admin_refresh: str | None = None
    stopped_reason: str | None = None

    parsed_base = urlsplit(BASE_URL)
    if parsed_base.scheme not in {"http", "https"} or not parsed_base.netloc:
        print("Noto'g'ri TOIR_API_BASE_URL; http(s) URL talab qilinadi.")
        return 2

    admin_email = getpass.getpass("Admin email: ").strip()
    admin_password = getpass.getpass("Admin password: ")
    if not admin_email or not admin_password:
        checks.append(Check("Admin credentials", False, "Email/password bo'sh"))
        print_results(checks)
        return 1

    try:
        login = request(
            "POST",
            "/api/v1/auth/login",
            payload={"email": admin_email, "password": admin_password},
        )
        require_status(checks, "Admin login", login, 200)
        admin_tokens = parse_object(login)
        admin_access = required_text(admin_tokens, "access_token")
        admin_refresh = required_text(admin_tokens, "refresh_token")
        admin_me = request("GET", "/api/v1/auth/me", bearer=admin_access)
        check_status(checks, "Admin /me", admin_me, 200)

        rotated = request(
            "POST",
            "/api/v1/auth/refresh",
            payload={"refresh_token": admin_refresh},
        )
        require_status(checks, "Refresh token rotation", rotated, 200)
        rotated_tokens = parse_object(rotated)
        admin_access = required_text(rotated_tokens, "access_token")
        next_refresh = required_text(rotated_tokens, "refresh_token")

        old_refresh = request(
            "POST",
            "/api/v1/auth/refresh",
            payload={"refresh_token": admin_refresh},
        )
        check_status(checks, "Reused refresh token rejected", old_refresh, 401)
        admin_refresh = next_refresh

        user_response, email, password = create_test_user(admin_access, "user")
        require_status(checks, "Create regular smoke user", user_response, 201)
        user_id = parse_object(user_response).get("id")
        if not isinstance(user_id, str):
            raise SmokeError("User creation response did not include an ID")
        user = TestUser(user_id, email, password)
        users.append(user)

        limiter_response, limiter_email, limiter_password = create_test_user(
            admin_access, "limiter"
        )
        require_status(checks, "Create rate-limit smoke user", limiter_response, 201)
        limiter_id = required_text(parse_object(limiter_response), "id")
        limiter_user = TestUser(limiter_id, limiter_email, limiter_password)
        users.append(limiter_user)

        wrong_password = request(
            "POST",
            "/api/v1/auth/login",
            payload={"email": user.email, "password": secrets.token_urlsafe(32)},
        )
        check_status(checks, "Incorrect password rejected", wrong_password, 401)

        user_login = request(
            "POST",
            "/api/v1/auth/login",
            payload={"email": user.email, "password": user.password},
        )
        check_status(checks, "Regular user login", user_login, 200)
        user_access: str | None = None
        if user_login.status == 200:
            user_access = required_text(parse_object(user_login), "access_token")
            forbidden = request("GET", "/api/v1/users", bearer=user_access)
            check_status(checks, "Regular user denied /users", forbidden, 403)

        no_token = request("GET", "/api/v1/users")
        check_status(checks, "Tokens absent -> /users unauthorized", no_token, 401)

        for attempt in range(1, 6):
            failure = request(
                "POST",
                "/api/v1/auth/login",
                payload={
                    "email": limiter_user.email,
                    "password": secrets.token_urlsafe(32),
                },
            )
            check_status(
                checks,
                f"Rate limit bad login {attempt}/5",
                failure,
                401,
            )
        limited = request(
            "POST",
            "/api/v1/auth/login",
            payload={
                "email": limiter_user.email,
                "password": secrets.token_urlsafe(32),
            },
        )
        check_status(checks, "Five failures trigger rate limit", limited, 429)

        cors = request(
            "OPTIONS",
            "/api/v1/auth/login",
            headers={
                "Origin": FOREIGN_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        allow_origin = cors.headers.get("access-control-allow-origin")
        check_condition(
            checks,
            "Foreign Origin not allowed by CORS",
            allow_origin not in {FOREIGN_ORIGIN, "*"},
            "No matching Access-Control-Allow-Origin header"
            if allow_origin not in {FOREIGN_ORIGIN, "*"}
            else "Foreign origin was allowed",
        )

        deactivated = request(
            "PATCH",
            f"/api/v1/users/{user.user_id}",
            bearer=admin_access,
            payload={"is_active": False},
        )
        if check_status(checks, "Deactivate regular smoke user", deactivated, 200):
            response_user = parse_object(deactivated)
            user.inactive = response_user.get("is_active") is False
            check_condition(
                checks,
                "Smoke user persisted as inactive",
                response_user.get("is_active") is False,
                "is_active is false"
                if response_user.get("is_active") is False
                else "API response did not confirm is_active=false",
            )

        inactive_login = request(
            "POST",
            "/api/v1/auth/login",
            payload={"email": user.email, "password": user.password},
        )
        check_status(checks, "Inactive user cannot log in", inactive_login, 401)

        if user_access is not None:
            inactive_access = request(
                "GET", "/api/v1/users", bearer=user_access
            )
            check_status(
                checks,
                "Inactive user's existing access token rejected",
                inactive_access,
                401,
            )

        logout = request(
            "POST",
            "/api/v1/auth/logout",
            payload={"refresh_token": admin_refresh},
        )
        require_status(checks, "Logout", logout, 204)
        after_logout = request(
            "POST",
            "/api/v1/auth/refresh",
            payload={"refresh_token": admin_refresh},
        )
        check_status(checks, "Logged-out refresh token rejected", after_logout, 401)
    except SmokeError as exc:
        stopped_reason = str(exc)
    finally:
        if admin_access is not None:
            for index, user in enumerate(users, start=1):
                if user.inactive:
                    continue
                try:
                    response = request(
                        "PATCH",
                        f"/api/v1/users/{user.user_id}",
                        bearer=admin_access,
                        payload={"is_active": False},
                    )
                    passed = response.status == 200
                    confirmed = False
                    if passed:
                        confirmed = parse_object(response).get("is_active") is False
                    check_condition(
                        checks,
                        f"Final cleanup: smoke user {index} inactive",
                        passed and confirmed,
                        "is_active=false confirmed"
                        if passed and confirmed
                        else f"HTTP {response.status}; inactive state not confirmed",
                    )
                except SmokeError:
                    check_condition(
                        checks,
                        f"Final cleanup: smoke user {index} inactive",
                        False,
                        "Could not confirm is_active=false",
                    )

    if stopped_reason is not None:
        print(f"\nSmoke test to'xtadi: {stopped_reason}")
    print_results(checks)
    return 1 if stopped_reason or any(not check.passed for check in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
