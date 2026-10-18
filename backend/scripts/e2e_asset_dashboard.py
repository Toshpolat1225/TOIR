"""Check fixed-asset dashboard totals and server-side section scope."""

from __future__ import annotations

import getpass
import sys
import uuid
from typing import Any

from e2e_refs import _record_created
from e2e_smoke import (
    ApiSession, Check, SmokeError, check_condition, check_status,
    create_test_user, parse_object, print_results, request, require_status,
)


def object_items(response: Any) -> list[dict[str, Any]]:
    data = parse_object(response)
    items = data.get("items")
    if not isinstance(items, list):
        raise SmokeError("API list response did not contain items")
    return items


def main() -> int:
    checks: list[Check] = []
    created_assets: list[str] = []
    admin_token: str | None = None
    master_id: str | None = None
    master_token: str | None = None
    email = getpass.getpass("Admin email: ").strip()
    password = getpass.getpass("Admin password: ")
    if not email or not password:
        print("Admin credentials are required.")
        return 2
    suffix = uuid.uuid4().hex[:12]
    session = ApiSession()
    sections: list[dict[str, Any]] = []
    try:
        login = request("POST", "/api/v1/auth/login", payload={"email": email, "password": password}, session=session)
        require_status(checks, "Admin login", login, 200)
        admin_token = parse_object(login).get("access_token")
        if not isinstance(admin_token, str) or not admin_token:
            raise SmokeError("Admin login did not return an access token")

        unauth = request("GET", "/api/v1/fixed-assets/stats")
        check_status(checks, "Dashboard stats require authentication", unauth, 401)
        sections_response = request("GET", "/api/v1/sections?limit=500", bearer=admin_token)
        require_status(checks, "Load sections", sections_response, 200)
        sections = object_items(sections_response)
        catalogs = request("GET", "/api/v1/fixed-asset-catalogs/types?limit=500&is_active=true", bearer=admin_token)
        require_status(checks, "Load active asset types", catalogs, 200)
        types = object_items(catalogs)
        statuses_response = request("GET", "/api/v1/fixed-asset-catalogs/statuses?limit=500&is_active=true", bearer=admin_token)
        require_status(checks, "Load active asset statuses", statuses_response, 200)
        statuses = object_items(statuses_response)
        if not types or not statuses:
            raise SmokeError("At least one active type and status are required for this check")

        blank = request("GET", f"/api/v1/fixed-assets?q=e2e_no_match_{suffix}", bearer=admin_token)
        require_status(checks, "Empty asset list", blank, 200)
        blank_stats = request("GET", f"/api/v1/fixed-assets/stats?q=e2e_no_match_{suffix}", bearer=admin_token)
        require_status(checks, "Empty dashboard stats", blank_stats, 200)
        check_condition(checks, "Empty filter returns zero and empty rows",
                        parse_object(blank).get("total") == 0 and parse_object(blank_stats).get("total") == 0,
                        "Both endpoints return zero")

        section_ids = [item.get("id") for item in sections if isinstance(item.get("id"), str)]
        assets_to_create = 2 if len(section_ids) > 1 else 1
        for index in range(assets_to_create):
            payload = {
                "inv_number": f"E2E-DASH-{suffix}-{index}",
                "name": f"E2E dashboard {suffix} {index}",
                "asset_type": types[index % len(types)]["code"],
                "status": statuses[index % len(statuses)]["code"],
                "mileage": 0,
            }
            if section_ids:
                payload["section_id"] = section_ids[index]
            response = request("POST", "/api/v1/fixed-assets", bearer=admin_token, payload=payload)
            require_status(checks, f"Create dashboard fixture {index + 1}", response, 201)
            asset_id = parse_object(response).get("id")
            if not isinstance(asset_id, str):
                raise SmokeError("Created asset id missing")
            created_assets.append(asset_id)

        list_response = request("GET", f"/api/v1/fixed-assets?q=E2E-DASH-{suffix}", bearer=admin_token)
        require_status(checks, "List dashboard fixtures", list_response, 200)
        list_data = parse_object(list_response)
        stats_response = request("GET", f"/api/v1/fixed-assets/stats?q=E2E-DASH-{suffix}", bearer=admin_token)
        require_status(checks, "Count dashboard fixtures", stats_response, 200)
        stats_data = parse_object(stats_response)
        check_condition(checks, "Dashboard total matches list total",
                        stats_data.get("total") == list_data.get("total") == len(created_assets),
                        f"Both totals match {len(created_assets)} fixtures")
        check_condition(checks, "Type facet counts add up to dashboard total",
                        sum(parse_object(stats_response).get("by_asset_type", {}).values()) == len(created_assets),
                        "Type facet count matches fixture count")
        behavior_by_code = {item.get("code"): item.get("behavior") for item in statuses}

        for asset in object_items(list_response):
            asset_type = asset["asset_type"]
            status_code = asset["status"]
            filtered_list = request("GET", f"/api/v1/fixed-assets?asset_type={asset_type}&q=E2E-DASH-{suffix}", bearer=admin_token)
            filtered_stats = request("GET", f"/api/v1/fixed-assets/stats?asset_type={asset_type}&q=E2E-DASH-{suffix}", bearer=admin_token)
            require_status(checks, "Type-filtered asset list", filtered_list, 200)
            require_status(checks, "Type-filtered dashboard stats", filtered_stats, 200)
            check_condition(checks, f"Type facet matches list ({asset_type})",
                            parse_object(filtered_list).get("total") == parse_object(filtered_stats).get("total"),
                            "Filtered totals match")
            status_list = request("GET", f"/api/v1/fixed-assets?status={status_code}&q=E2E-DASH-{suffix}", bearer=admin_token)
            status_stats = request("GET", f"/api/v1/fixed-assets/stats?status={status_code}&q=E2E-DASH-{suffix}", bearer=admin_token)
            require_status(checks, "Status-filtered asset list", status_list, 200)
            require_status(checks, "Status-filtered dashboard stats", status_stats, 200)
            check_condition(checks, f"Status filter matches list ({status_code})",
                            parse_object(status_list).get("total") == parse_object(status_stats).get("total"),
                            "Filtered totals match")
            behavior = behavior_by_code.get(status_code)
            if behavior:
                behavior_list = request("GET", f"/api/v1/fixed-assets?status_behavior={behavior}&q=E2E-DASH-{suffix}", bearer=admin_token)
                behavior_stats = request("GET", f"/api/v1/fixed-assets/stats?status_behavior={behavior}&q=E2E-DASH-{suffix}", bearer=admin_token)
                require_status(checks, "Behavior-filtered asset list", behavior_list, 200)
                require_status(checks, "Behavior-filtered dashboard stats", behavior_stats, 200)
                check_condition(checks, f"Behavior filter matches list ({behavior})",
                                parse_object(behavior_list).get("total") == parse_object(behavior_stats).get("total"),
                                "Filtered totals match")

        if len(section_ids) > 1:
            user_response, user_email, user_password = create_test_user(admin_token, "asset-dashboard-master")
            master_id = _record_created(checks, [], "Create temporary master", user_response, "/api/v1/users")
            changed = request("PATCH", f"/api/v1/users/{master_id}", bearer=admin_token,
                              payload={"role": "master", "section_id": section_ids[0]})
            require_status(checks, "Assign master section", changed, 200)
            master_login = request("POST", "/api/v1/auth/login", payload={"email": user_email, "password": user_password}, session=ApiSession())
            require_status(checks, "Master login", master_login, 200)
            master_token = parse_object(master_login).get("access_token")
            master_counts = request("GET", f"/api/v1/fixed-assets/stats?section_id={section_ids[1]}&q=E2E-DASH-{suffix}", bearer=master_token)
            require_status(checks, "Master dashboard stats", master_counts, 200)
            expected = sum(1 for asset in object_items(list_response) if asset.get("section_id") == section_ids[0])
            check_condition(checks, "Master scope overrides requested section",
                            parse_object(master_counts).get("total") == expected,
                            "Only fixtures from the assigned section are counted")
        else:
            check_condition(checks, "Master scope test needs two existing sections", False,
                            "Skipped: API returned fewer than two sections")
    except SmokeError as exc:
        print(f"Dashboard check stopped: {exc}")
        return 1
    finally:
        if admin_token:
            for asset_id in reversed(created_assets):
                response = request("DELETE", f"/api/v1/fixed-assets/{asset_id}", bearer=admin_token)
                check_condition(checks, "Remove dashboard fixture", response.status in {204, 404}, f"HTTP {response.status}")
            if master_id:
                request("PATCH", f"/api/v1/users/{master_id}", bearer=admin_token,
                        payload={"role": "operator", "section_id": None, "is_active": False})
    print_results(checks)
    return 1 if any(not item.passed for item in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
