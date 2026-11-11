"""Exercise GTK matching, manual links, and dry-run creation against a test API."""

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
    require_status,
)


def _items(response: Any) -> list[dict[str, Any]]:
    payload = parse_object(response)
    items = payload.get("items")
    if not isinstance(items, list) or not all(
        isinstance(item, dict) for item in items
    ):
        raise SmokeError("GTK list response is not a paginated object")
    return items


def main() -> int:
    checks: list[Check] = []
    created_assets: list[str] = []
    linked_asset_id: str | None = None
    gtk_id: int | None = None
    token: str | None = None
    stopped_reason: str | None = None

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

        for path, label in (
            ("/api/v1/gtk/locomotives?limit=5", "GTK locomotives"),
            ("/api/v1/gtk/carriages?limit=5", "GTK carriages"),
        ):
            response = request("GET", path, bearer=token)
            require_status(checks, label, response, 200)
            items = _items(response)
            check_condition(
                checks,
                f"{label} match fields",
                all("linked_asset" in item and "suggestion" in item for item in items),
                "Each row includes link and suggestion fields",
            )
            proposals_are_exact = True
            ambiguous_proposals_are_unselected = True
            for item in items:
                suggestion = item.get("suggestion")
                if not isinstance(suggestion, dict):
                    proposals_are_exact = False
                    ambiguous_proposals_are_unselected = False
                    continue
                if suggestion.get("level") == "high":
                    candidate = suggestion.get("asset")
                    proposals_are_exact = proposals_are_exact and (
                        isinstance(item.get("inventory_number"), str)
                        and bool(item["inventory_number"].strip())
                        and isinstance(candidate, dict)
                        and candidate.get("inv_number") == item["inventory_number"]
                    )
                if suggestion.get("level") == "ambiguous":
                    ambiguous_proposals_are_unselected = (
                        ambiguous_proposals_are_unselected
                        and suggestion.get("asset") is None
                    )
            check_condition(
                checks,
                f"{label} exact inventory proposals",
                proposals_are_exact and ambiguous_proposals_are_unselected,
                "Only unique exact inventory matches select an asset",
            )

        for kind in ("locomotive", "carriage"):
            json_report = request(
                "GET",
                f"/api/v1/gtk/match-report?kind={kind}",
                bearer=token,
            )
            require_status(checks, f"{kind} JSON match report", json_report, 200)
            report_body = parse_object(json_report)
            check_condition(
                checks,
                f"{kind} JSON report shape",
                report_body.get("kind") == kind
                and isinstance(report_body.get("totals"), dict)
                and isinstance(report_body.get("items"), list),
                "Report kind, totals, and items are present",
            )
            csv_report = request(
                "GET",
                f"/api/v1/gtk/match-report?kind={kind}&format=csv",
                bearer=token,
            )
            require_status(checks, f"{kind} CSV match report", csv_report, 200)
            check_condition(
                checks,
                f"{kind} CSV report shape",
                "text/csv" in csv_report.headers.get("content-type", "")
                and csv_report.body.startswith(b"gtk_id,kind,level,"),
                "CSV content type and header are present",
            )

        carriage_response = request(
            "GET",
            "/api/v1/gtk/carriages?is_active=true&duplicate=false&limit=1000",
            bearer=token,
        )
        require_status(checks, "Eligible GTK carriages", carriage_response, 200)
        carriages = _items(carriage_response)
        eligible = next(
            (
                item
                for item in carriages
                if isinstance(item.get("gtk_id"), int)
                and item.get("linked_asset") is None
            ),
            None,
        )
        if eligible is None:
            raise SmokeError("No unlinked active GTK carriage is available for link checks")
        gtk_id = eligible["gtk_id"]

        for path, label in (
            (
                f"/api/v1/gtk/carriages/{gtk_id}/create-asset",
                "Single carriage dry run",
            ),
            ("/api/v1/gtk/carriages/create-assets", "Bulk carriage dry run"),
        ):
            response = request(
                "POST", path, bearer=token, payload={"dry_run": True}
            )
            require_status(checks, label, response, 200)
            body = parse_object(response)
            check_condition(
                checks,
                f"{label} does not write",
                body.get("dry_run") is True
                and body.get("created") == 0
                and isinstance(body.get("items"), list),
                "Dry-run response reports zero created assets",
            )

        suffix = uuid.uuid4().hex
        asset_response = request(
            "POST",
            "/api/v1/fixed-assets",
            bearer=token,
            payload={
                "inv_number": f"GTK-LINK-E2E-{suffix}",
                "name": f"GTK link test {suffix}",
                "asset_type": "wagon",
                "series": "GTK-E2E-WAGON",
                "number": f"1{suffix[-4:]}",
                "status": "operational",
                "mileage": 0,
            },
        )
        require_status(checks, "Create temporary wagon", asset_response, 201)
        linked_asset_id = parse_object(asset_response).get("id")
        if not isinstance(linked_asset_id, str):
            raise SmokeError("Temporary fixed asset response did not contain an ID")
        created_assets.append(linked_asset_id)

        stale_proposal = request(
            "POST",
            "/api/v1/gtk/links",
            bearer=token,
            payload={
                "links": [
                    {
                        "asset_id": linked_asset_id,
                        "gtk_id": gtk_id,
                        "kind": "carriage",
                        "expected_inventory_number": f"STALE-{suffix}",
                    }
                ]
            },
        )
        check_status(
            checks, "Stale inventory proposal is rejected", stale_proposal, 409
        )

        link_response = request(
            "POST",
            "/api/v1/gtk/links",
            bearer=token,
            payload={
                "links": [
                    {
                        "asset_id": linked_asset_id,
                        "gtk_id": gtk_id,
                        "kind": "carriage",
                    }
                ]
            },
        )
        require_status(checks, "Create manual GTK link", link_response, 200)
        check_condition(
            checks,
            "Manual GTK link count",
            parse_object(link_response).get("updated") == 1,
            "One user-confirmed link was saved",
        )

        duplicate_response = request(
            "POST",
            "/api/v1/fixed-assets",
            bearer=token,
            payload={
                "inv_number": f"GTK-DUP-E2E-{suffix}",
                "name": f"GTK duplicate test {suffix}",
                "asset_type": "wagon",
                "series": "GTK-E2E-WAGON",
                "number": f"2{suffix[-4:]}",
                "gtk_id": str(gtk_id),
            },
        )
        check_status(checks, "Duplicate GTK ID is rejected", duplicate_response, 409)
        if duplicate_response.status in {200, 201}:
            unexpected_id = parse_object(duplicate_response).get("id")
            if isinstance(unexpected_id, str):
                created_assets.append(unexpected_id)

        mismatch_response = request(
            "POST",
            "/api/v1/fixed-assets",
            bearer=token,
            payload={
                "inv_number": f"GTK-TYPE-E2E-{suffix}",
                "name": f"GTK type test {suffix}",
                "asset_type": "locomotive",
                "series": "GTK-E2E-LOCO",
                "number": f"3{suffix[-4:]}",
                "gtk_id": str(gtk_id),
            },
        )
        check_status(checks, "GTK type mismatch is rejected", mismatch_response, 422)
        if mismatch_response.status in {200, 201}:
            unexpected_id = parse_object(mismatch_response).get("id")
            if isinstance(unexpected_id, str):
                created_assets.append(unexpected_id)

        linked_rows = _items(
            request(
                "GET",
                "/api/v1/gtk/carriages?limit=1000",
                bearer=token,
            )
        )
        linked_row = next(
            (item for item in linked_rows if item.get("gtk_id") == gtk_id), {}
        )
        check_condition(
            checks,
            "Linked carriage response",
            (linked_row.get("linked_asset") or {}).get("id") == linked_asset_id,
            "Carriage shows its explicitly linked fixed asset",
        )

        unlink_response = request(
            "DELETE",
            f"/api/v1/gtk/links/{linked_asset_id}",
            bearer=token,
        )
        require_status(checks, "Delete GTK link", unlink_response, 204)
        linked_asset_id = None
    except SmokeError as exc:
        stopped_reason = str(exc)
    finally:
        if token is not None:
            if linked_asset_id is not None:
                response = request(
                    "DELETE",
                    f"/api/v1/gtk/links/{linked_asset_id}",
                    bearer=token,
                )
                check_condition(
                    checks,
                    "Cleanup: remove temporary GTK link",
                    response.status in {204, 404},
                    f"HTTP {response.status}",
                )
            for asset_id in reversed(created_assets):
                response = request(
                    "DELETE",
                    f"/api/v1/fixed-assets/{asset_id}",
                    bearer=token,
                )
                check_condition(
                    checks,
                    "Cleanup: delete temporary fixed asset",
                    response.status in {204, 404},
                    f"HTTP {response.status}",
                )

    if stopped_reason:
        print(f"Stopped: {stopped_reason}")
    print_results(checks)
    return 1 if stopped_reason or any(not item.passed for item in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
