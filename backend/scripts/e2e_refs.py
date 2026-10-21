"""Exercise reference-data CRUD and authorization against the API tunnel.

Run only after the backend deployment containing these routes is available.
"""

from __future__ import annotations

import getpass
import secrets
import sys
import uuid
from typing import Any
from urllib.parse import urlencode

from e2e_smoke import (
    ApiSession,
    Check,
    SmokeError,
    check_condition,
    check_status,
    create_test_user,
    parse_object,
    print_results,
    request,
    require_status,
)


def _required_id(payload: dict[str, Any]) -> str:
    value = payload.get("id")
    if not isinstance(value, str) or not value:
        raise SmokeError("API response did not include a record ID")
    return value


def _record_created(
    checks: list[Check],
    resources: list[tuple[str, str]],
    label: str,
    response: Any,
    endpoint: str,
) -> str:
    require_status(checks, label, response, 201)
    record_id = _required_id(parse_object(response))
    resources.append((endpoint, record_id))
    return record_id


def _check_item(response: Any, record_id: str) -> bool:
    try:
        return parse_object(response).get("id") == record_id
    except SmokeError:
        return False


def main() -> int:
    checks: list[Check] = []
    users: list[tuple[str, bool]] = []
    resources: list[tuple[str, str]] = []
    admin_token: str | None = None
    operator_token: str | None = None
    master_token: str | None = None
    admin_session = ApiSession()

    admin_email = getpass.getpass("Admin email: ").strip()
    admin_password = getpass.getpass("Admin password: ")
    if not admin_email or not admin_password:
        print("Admin email and password are required.")
        return 2

    suffix = uuid.uuid4().hex
    department_id: str | None = None
    foreign_department_id: str | None = None
    section_id: str | None = None
    foreign_section_id: str | None = None
    hierarchy_parent_id: str | None = None
    hierarchy_child_id: str | None = None
    hierarchy_leaf_id: str | None = None
    hierarchy_other_root_id: str | None = None
    employee_id: str | None = None
    foreign_employee_id: str | None = None
    work_type_id: str | None = None
    subtask_id: str | None = None
    template_id: str | None = None
    interval_id: str | None = None
    stopped_reason: str | None = None

    try:
        login = request(
            "POST",
            "/api/v1/auth/login",
            payload={"email": admin_email, "password": admin_password},
            session=admin_session,
        )
        require_status(checks, "Admin login", login, 200)
        admin_token = parse_object(login).get("access_token")
        if not isinstance(admin_token, str) or not admin_token:
            raise SmokeError("Admin login response did not include an access token")

        operator_response, operator_email, operator_password = create_test_user(
            admin_token, "reference-operator"
        )
        operator_id = _record_created(
            checks, [], "Create temporary operator", operator_response, "/api/v1/users"
        )
        users.append((operator_id, False))
        operator_login = request(
            "POST",
            "/api/v1/auth/login",
            payload={"email": operator_email, "password": operator_password},
            session=ApiSession(),
        )
        require_status(checks, "Operator login", operator_login, 200)
        operator_token = parse_object(operator_login).get("access_token")
        if not isinstance(operator_token, str) or not operator_token:
            raise SmokeError("Operator login response did not include an access token")

        department_response = request(
            "POST",
            "/api/v1/departments",
            bearer=operator_token,
            payload={"name": f"Reference test {suffix}", "color": "#123456"},
        )
        department_id = _record_created(
            checks,
            resources,
            "Create department",
            department_response,
            "/api/v1/departments",
        )
        section_response = request(
            "POST",
            "/api/v1/sections",
            bearer=operator_token,
            payload={"name": f"REF-{suffix[:10]}", "department_id": department_id},
        )
        section_id = _record_created(
            checks, resources, "Create master section", section_response, "/api/v1/sections"
        )

        foreign_department_response = request(
            "POST",
            "/api/v1/departments",
            bearer=operator_token,
            payload={"name": f"Reference foreign {suffix}", "color": "#654321"},
        )
        foreign_department_id = _record_created(
            checks,
            resources,
            "Create second department",
            foreign_department_response,
            "/api/v1/departments",
        )
        foreign_section_response = request(
            "POST",
            "/api/v1/sections",
            bearer=operator_token,
            payload={
                "name": f"REF-OTHER-{suffix[:8]}",
                "department_id": foreign_department_id,
            },
        )
        foreign_section_id = _record_created(
            checks,
            resources,
            "Create foreign section",
            foreign_section_response,
            "/api/v1/sections",
        )

        master_email = f"reference-master-{suffix}@example.invalid"
        master_password = secrets.token_urlsafe(32)
        master_response = request(
            "POST",
            "/api/v1/users",
            bearer=admin_token,
            payload={
                "email": master_email,
                "full_name": "Reference test master",
                "password": master_password,
                "role": "master",
                "section_id": section_id,
                "is_active": True,
            },
        )
        master_id = _record_created(
            checks, [], "Create temporary master", master_response, "/api/v1/users"
        )
        users.append((master_id, True))
        master_login = request(
            "POST",
            "/api/v1/auth/login",
            payload={"email": master_email, "password": master_password},
            session=ApiSession(),
        )
        require_status(checks, "Master login", master_login, 200)
        master_token = parse_object(master_login).get("access_token")
        if not isinstance(master_token, str) or not master_token:
            raise SmokeError("Master login response did not include an access token")

        # Department list/get/update and the referenced-delete conflict.
        department_list = request("GET", "/api/v1/departments", bearer=operator_token)
        require_status(checks, "List departments", department_list, 200)
        department_get = request(
            "GET", f"/api/v1/departments/{department_id}", bearer=operator_token
        )
        check_condition(
            checks,
            "Get department",
            department_get.status == 200 and _check_item(department_get, department_id),
            f"HTTP {department_get.status}; returned expected record"
            if department_get.status == 200 and _check_item(department_get, department_id)
            else f"HTTP {department_get.status}; expected created record",
        )
        department_update = request(
            "PATCH",
            f"/api/v1/departments/{department_id}",
            bearer=operator_token,
            payload={"color": "#234567"},
        )
        check_status(checks, "Update department", department_update, 200)
        check_status(
            checks,
            "Referenced department delete returns 409",
            request(
                "DELETE",
                f"/api/v1/departments/{department_id}",
                bearer=operator_token,
            ),
            409,
        )

        # Section reads for a master are server-scoped, not client-filtered.
        section_list = request(
            "GET", "/api/v1/sections?limit=1000", bearer=operator_token
        )
        require_status(checks, "List sections", section_list, 200)
        section_get = request(
            "GET", f"/api/v1/sections/{section_id}", bearer=operator_token
        )
        check_condition(
            checks,
            "Get section",
            section_get.status == 200 and _check_item(section_get, section_id),
            f"HTTP {section_get.status}; returned expected record"
            if section_get.status == 200 and _check_item(section_get, section_id)
            else f"HTTP {section_get.status}; expected created record",
        )
        section_update = request(
            "PATCH",
            f"/api/v1/sections/{section_id}",
            bearer=operator_token,
            payload={"name": f"REF-UPD-{suffix[:8]}"},
        )
        check_status(checks, "Update section", section_update, 200)
        section_search = request(
            "GET",
            f"/api/v1/sections?limit=25&q=REF-UPD-{suffix[:8]}",
            bearer=operator_token,
        )
        section_search_items = parse_object(section_search).get("items", [])
        check_condition(
            checks,
            "Section search is server-side and paginated",
            section_search.status == 200
            and parse_object(section_search).get("total") == 1
            and len(section_search_items) == 1
            and section_search_items[0].get("id") == section_id,
            f"HTTP {section_search.status}; total and matching row checked",
        )
        master_sections = request(
            "GET", "/api/v1/sections?limit=1000", bearer=master_token
        )
        master_section_items = parse_object(master_sections).get("items", [])
        check_condition(
            checks,
            "Master sees only own section",
            master_sections.status == 200
            and [item.get("id") for item in master_section_items] == [section_id],
            "List is constrained to assigned section"
            if master_sections.status == 200
            and [item.get("id") for item in master_section_items] == [section_id]
            else f"HTTP {master_sections.status}; section scope was not enforced",
        )
        master_tree = request(
            "GET", "/api/v1/sections/tree", bearer=master_token
        )
        master_tree_items = master_tree.json() if master_tree.status == 200 else []
        check_condition(
            checks,
            "Master tree is scoped to own section",
            len(master_tree_items) == 1
            and master_tree_items[0].get("id") == section_id
            and not master_tree_items[0].get("children"),
            f"HTTP {master_tree.status}; own unit only",
        )
        master_filtered_sections = request(
            "GET",
            f"/api/v1/sections?limit=25&q=REF-UPD-{suffix[:8]}",
            bearer=master_token,
        )
        master_filtered_items = parse_object(master_filtered_sections).get("items", [])
        check_condition(
            checks,
            "Master search retains assigned-section scope",
            master_filtered_sections.status == 200
            and [item.get("id") for item in master_filtered_items] == [section_id],
            f"HTTP {master_filtered_sections.status}; only assigned section returned",
        )
        check_status(
            checks,
            "Master cannot read another section",
            request(
                "GET",
                f"/api/v1/sections/{foreign_section_id}",
                bearer=master_token,
            ),
            404,
        )
        check_status(
            checks,
            "Master cannot write",
            request(
                "POST",
                "/api/v1/departments",
                bearer=master_token,
                payload={"name": f"Forbidden {suffix}", "color": "#000000"},
            ),
            403,
        )
        check_status(
            checks,
            "Master cannot create hierarchy units",
            request(
                "POST",
                "/api/v1/sections",
                bearer=master_token,
                payload={"name": f"Forbidden unit {suffix}"},
            ),
            403,
        )

        hierarchy_parent = request(
            "POST",
            "/api/v1/sections",
            bearer=operator_token,
            payload={
                "name": f"HIER-RU-{suffix[:8]}",
                "unit_type": "department",
                "translations": {
                    "ru": f"HIER-RU-{suffix[:8]}",
                    "uz-Latn": f"HIER-LAT-{suffix[:8]}",
                    "uz-Cyrl": f"HIER-CYR-{suffix[:8]}",
                },
            },
        )
        hierarchy_parent_id = _record_created(
            checks, resources, "Create translated hierarchy root",
            hierarchy_parent, "/api/v1/sections",
        )
        check_status(
            checks,
            "Master cannot modify hierarchy units",
            request(
                "PATCH",
                f"/api/v1/sections/{hierarchy_parent_id}",
                bearer=master_token,
                payload={"name": f"Forbidden update {suffix}"},
            ),
            403,
        )
        check_status(
            checks,
            "Master cannot archive hierarchy units",
            request(
                "DELETE",
                f"/api/v1/sections/{hierarchy_parent_id}",
                bearer=master_token,
            ),
            403,
        )
        hierarchy_child = request(
            "POST",
            "/api/v1/sections",
            bearer=operator_token,
            payload={
                "name": f"HIER-DIV-{suffix[:8]}",
                "parent_id": hierarchy_parent_id,
                "unit_type": "division",
                "translations": {
                    "ru": f"HIER-DIV-{suffix[:8]}",
                    "uz-Latn": f"HIER-DIVLAT-{suffix[:8]}",
                    "uz-Cyrl": f"HIER-DIVCYR-{suffix[:8]}",
                },
            },
        )
        hierarchy_child_id = _record_created(
            checks, resources, "Create typed child unit",
            hierarchy_child, "/api/v1/sections",
        )
        hierarchy_leaf = request(
            "POST",
            "/api/v1/sections",
            bearer=operator_token,
            payload={
                "name": f"HIER-SEC-{suffix[:8]}",
                "parent_id": hierarchy_child_id,
                "unit_type": "division",
                "translations": {
                    "ru": f"HIER-SEC-{suffix[:8]}",
                    "uz-Latn": f"HIER-SECLAT-{suffix[:8]}",
                    "uz-Cyrl": f"HIER-SECCYR-{suffix[:8]}",
                },
            },
        )
        hierarchy_leaf_id = _record_created(
            checks, resources, "Create third-level unit",
            hierarchy_leaf, "/api/v1/sections",
        )
        check_status(
            checks,
            "Division cannot have a section parent",
            request(
                "POST",
                "/api/v1/sections",
                bearer=operator_token,
                payload={
                    "name": f"HIER-BAD-{suffix[:8]}",
                    "parent_id": section_id,
                    "unit_type": "division",
                },
            ),
            409,
        )
        hierarchy_other_root = request(
            "POST",
            "/api/v1/sections",
            bearer=operator_token,
            payload={
                "name": f"HIER-ALT-{suffix[:8]}",
                "unit_type": "department",
                "translations": {
                    "ru": f"HIER-ALT-{suffix[:8]}",
                    "uz-Latn": f"HIER-ALTLAT-{suffix[:8]}",
                    "uz-Cyrl": f"HIER-ALTCYR-{suffix[:8]}",
                },
            },
        )
        hierarchy_other_root_id = _record_created(
            checks, resources, "Create second hierarchy root",
            hierarchy_other_root, "/api/v1/sections",
        )
        move_to_other_root = request(
            "PATCH",
            f"/api/v1/sections/{hierarchy_child_id}",
            bearer=operator_token,
            payload={"parent_id": hierarchy_other_root_id},
        )
        moved_payload = parse_object(move_to_other_root) if move_to_other_root.status == 200 else {}
        check_condition(
            checks,
            "Move unit to compatible parent",
            move_to_other_root.status == 200
            and moved_payload.get("parent_id") == hierarchy_other_root_id,
            f"HTTP {move_to_other_root.status}; parent ID returned",
        )
        move_back = request(
            "PATCH",
            f"/api/v1/sections/{hierarchy_child_id}",
            bearer=operator_token,
            payload={"parent_id": hierarchy_parent_id},
        )
        check_status(checks, "Move unit back to original parent", move_back, 200)
        hierarchy_payload = parse_object(hierarchy_parent)
        check_condition(
            checks,
            "Section stores all three names",
            hierarchy_payload.get("translations") == {
                "ru": f"HIER-RU-{suffix[:8]}",
                "uz-Latn": f"HIER-LAT-{suffix[:8]}",
                "uz-Cyrl": f"HIER-CYR-{suffix[:8]}",
            },
            "Three translations returned on create response",
        )
        updated_translations = {
            "ru": f"HIER-SEC-UPD-{suffix[:8]}",
            "uz-Latn": f"HIER-SEC-UPDLAT-{suffix[:8]}",
            "uz-Cyrl": f"HIER-SEC-UPDCYR-{suffix[:8]}",
        }
        translation_update = request(
            "PATCH",
            f"/api/v1/sections/{hierarchy_leaf_id}",
            bearer=operator_token,
            payload={"translations": updated_translations},
        )
        translation_update_payload = (
            parse_object(translation_update) if translation_update.status == 200 else {}
        )
        check_condition(
            checks,
            "Update all section translations",
            translation_update.status == 200
            and translation_update_payload.get("translations") == updated_translations,
            f"HTTP {translation_update.status}; all values returned",
        )
        translation_get = request(
            "GET",
            f"/api/v1/sections/{hierarchy_leaf_id}",
            bearer=operator_token,
            headers={"Accept-Language": "uz-Latn"},
        )
        translation_payload = (
            parse_object(translation_get) if translation_get.status == 200 else {}
        )
        check_condition(
            checks,
            "Read Russian canonical and Uzbek localized names",
            translation_get.status == 200
            and translation_payload.get("name") == updated_translations["ru"]
            and translation_payload.get("localized_name") == updated_translations["uz-Latn"],
            f"HTTP {translation_get.status}; canonical and localized values checked",
        )
        translated_search = request(
            "GET",
            f"/api/v1/sections?limit=25&q=HIER-LAT-{suffix[:8]}",
            bearer=operator_token,
        )
        translated_items = parse_object(translated_search).get("items", [])
        check_condition(
            checks,
            "Section search includes Uzbek translations",
            translated_search.status == 200
            and any(item.get("id") == hierarchy_parent_id for item in translated_items),
            f"HTTP {translated_search.status}; localized-name search checked",
        )
        nested_tree_response = request(
            "GET",
            f"/api/v1/sections/tree?q=HIER-RU-{suffix[:8]}",
            bearer=operator_token,
        )
        require_status(checks, "Read nested hierarchy tree", nested_tree_response, 200)
        nested_tree = nested_tree_response.json()
        nested_ok = (
            isinstance(nested_tree, list)
            and len(nested_tree) == 1
            and nested_tree[0].get("id") == hierarchy_parent_id
            and len(nested_tree[0].get("children", [])) == 1
            and nested_tree[0]["children"][0].get("id") == hierarchy_child_id
            and nested_tree[0]["children"][0]["children"][0].get("id") == hierarchy_leaf_id
        )
        check_condition(
            checks, "Tree includes three levels", nested_ok,
            "Root, child, and grandchild IDs checked",
        )
        check_status(
            checks,
            "Cycle-causing move returns 409",
            request(
                "PATCH",
                f"/api/v1/sections/{hierarchy_child_id}",
                bearer=operator_token,
                payload={"parent_id": hierarchy_leaf_id},
            ),
            409,
        )
        check_status(
            checks,
            "Parent with active child cannot be archived",
            request(
                "DELETE",
                f"/api/v1/sections/{hierarchy_parent_id}",
                bearer=operator_token,
            ),
            409,
        )
        historical_employee_response = request(
            "POST",
            "/api/v1/employees",
            bearer=operator_token,
            payload={
                "tab_number": f"REF-HIST-{suffix[:8]}",
                "full_name": "Historical section link test",
                "section_id": hierarchy_leaf_id,
            },
        )
        historical_employee_id = _record_created(
            checks,
            resources,
            "Create employee with hierarchy reference",
            historical_employee_response,
            "/api/v1/employees",
        )
        check_status(
            checks,
            "Archive section with historical employee reference",
            request(
                "DELETE",
                f"/api/v1/sections/{hierarchy_leaf_id}",
                bearer=operator_token,
            ),
            204,
        )
        historical_employee_get = request(
            "GET",
            f"/api/v1/employees/{historical_employee_id}",
            bearer=operator_token,
        )
        historical_employee_payload = (
            parse_object(historical_employee_get)
            if historical_employee_get.status == 200
            else {}
        )
        check_condition(
            checks,
            "Archive preserves historical section foreign key",
            historical_employee_get.status == 200
            and historical_employee_payload.get("section_id") == hierarchy_leaf_id,
            f"HTTP {historical_employee_get.status}; historical ID retained",
        )
        for label, record_id in (
            ("Archive leaf unit", hierarchy_leaf_id),
            ("Archive middle unit", hierarchy_child_id),
            ("Archive hierarchy root", hierarchy_parent_id),
        ):
            check_status(
                checks,
                label,
                request(
                    "DELETE",
                    f"/api/v1/sections/{record_id}",
                    bearer=operator_token,
                ),
                204,
            )
        archived_tree = request(
            "GET",
            f"/api/v1/sections/tree?q=HIER-SEC-{suffix[:8]}&include_archived=true",
            bearer=operator_token,
        )
        archived_nodes = archived_tree.json() if archived_tree.status == 200 else []
        check_condition(
            checks,
            "Archived hierarchy retains all IDs",
            len(archived_nodes) == 1
            and archived_nodes[0].get("id") == hierarchy_parent_id
            and archived_nodes[0].get("is_archived") is True
            and archived_nodes[0]["children"][0]["children"][0].get("id") == hierarchy_leaf_id,
            f"HTTP {archived_tree.status}; archived tree inspected",
        )
        check_status(
            checks,
            "New employee cannot use an archived unit",
            request(
                "POST",
                "/api/v1/employees",
                bearer=operator_token,
                payload={
                    "tab_number": f"REF-ARCH-{suffix[:8]}",
                    "full_name": "Archived section test",
                    "section_id": hierarchy_parent_id,
                },
            ),
            422,
        )
        restore_parent = request(
            "PATCH",
            f"/api/v1/sections/{hierarchy_parent_id}",
            bearer=operator_token,
            payload={"is_archived": False},
        )
        check_status(checks, "Restore hierarchy root", restore_parent, 200)

        employee_response = request(
            "POST",
            "/api/v1/employees",
            bearer=operator_token,
            payload={
                "tab_number": f"REF-{suffix}",
                "full_name": "Reference Test Employee",
                "position": None,
                "section_id": section_id,
                "location_id": None,
            },
        )
        employee_id = _record_created(
            checks, resources, "Create employee", employee_response, "/api/v1/employees"
        )
        foreign_employee_response = request(
            "POST",
            "/api/v1/employees",
            bearer=operator_token,
            payload={
                "tab_number": f"REF-OTHER-{suffix}",
                "full_name": "Reference Foreign Employee",
                "position": None,
                "section_id": foreign_section_id,
                "location_id": None,
            },
        )
        foreign_employee_id = _record_created(
            checks,
            resources,
            "Create employee in foreign section",
            foreign_employee_response,
            "/api/v1/employees",
        )
        employee_list = request(
            "GET",
            f"/api/v1/employees?section_id={section_id}",
            bearer=operator_token,
        )
        require_status(checks, "List employees", employee_list, 200)
        employee_search = request(
            "GET",
            f"/api/v1/employees?{urlencode({'section_id': section_id, 'q': f'REF-{suffix}', 'is_active': 'true'})}",
            bearer=operator_token,
        )
        employee_search_items = parse_object(employee_search).get("items", []) if employee_search.status == 200 else []
        check_condition(
            checks,
            "Employee search, section, and active filters combine server-side",
            employee_search.status == 200 and len(employee_search_items) == 1 and employee_search_items[0].get("id") == employee_id,
            "Only the matching active employee is returned" if employee_search.status == 200 else f"HTTP {employee_search.status}",
        )
        employee_get = request(
            "GET", f"/api/v1/employees/{employee_id}", bearer=operator_token
        )
        check_condition(
            checks,
            "Get employee",
            employee_get.status == 200 and _check_item(employee_get, employee_id),
            f"HTTP {employee_get.status}; returned expected record"
            if employee_get.status == 200 and _check_item(employee_get, employee_id)
            else f"HTTP {employee_get.status}; expected created record",
        )
        master_employee_list = request(
            "GET",
            f"/api/v1/employees?section_id={foreign_section_id}&limit=1000",
            bearer=master_token,
        )
        master_employee_items = (
            parse_object(master_employee_list).get("items", [])
            if master_employee_list.status == 200
            else None
        )
        check_condition(
            checks,
            "Master employee list stays in own section with foreign section filter",
            isinstance(master_employee_items, list)
            and all(item.get("section_id") == section_id for item in master_employee_items)
            and all(item.get("id") != foreign_employee_id for item in master_employee_items),
            "Only employees from the master's own section are returned"
            if isinstance(master_employee_items, list)
            and all(item.get("section_id") == section_id for item in master_employee_items)
            and all(item.get("id") != foreign_employee_id for item in master_employee_items)
            else f"HTTP {master_employee_list.status}; employee scope was not enforced",
        )
        check_status(
            checks,
            "Master cannot read employee from another section",
            request(
                "GET",
                f"/api/v1/employees/{foreign_employee_id}",
                bearer=master_token,
            ),
            404,
        )
        check_status(
            checks,
            "Update employee",
            request(
                "PATCH",
                f"/api/v1/employees/{employee_id}",
                bearer=operator_token,
                payload={"full_name": "Reference Test Employee Updated"},
            ),
            200,
        )
        duplicate_employee = request(
            "POST",
            "/api/v1/employees",
            bearer=operator_token,
            payload={
                "tab_number": f"REF-{suffix}",
                "full_name": "Duplicate employee",
            },
        )
        check_status(checks, "Duplicate employee tab number returns 409", duplicate_employee, 409)
        check_status(
            checks,
            "Delete employee",
            request(
                "DELETE",
                f"/api/v1/employees/{employee_id}",
                bearer=operator_token,
            ),
            204,
        )
        resources.remove(("/api/v1/employees", employee_id))

        work_type_response = request(
            "POST",
            "/api/v1/work-types",
            bearer=operator_token,
            payload={
                "code": f"REF-{suffix[:10]}",
                "name": "Reference test work type",
                "description": None,
                "unit_type": "locomotive",
                "sort_order": 900,
            },
        )
        work_type_id = _record_created(
            checks, resources, "Create work type", work_type_response, "/api/v1/work-types"
        )
        work_type_code = parse_object(work_type_response)["code"]
        work_type_search = request(
            "GET", f"/api/v1/work-types?{urlencode({'q': work_type_code})}", bearer=operator_token
        )
        work_type_items = parse_object(work_type_search).get("items", []) if work_type_search.status == 200 else []
        check_condition(
            checks,
            "Work-type code search is server-side",
            work_type_search.status == 200 and len(work_type_items) == 1 and work_type_items[0].get("id") == work_type_id,
            "Matching work type returned" if work_type_search.status == 200 else f"HTTP {work_type_search.status}",
        )
        check_status(
            checks,
            "List work types",
            request("GET", "/api/v1/work-types", bearer=operator_token),
            200,
        )
        work_type_get = request(
            "GET", f"/api/v1/work-types/{work_type_id}", bearer=operator_token
        )
        check_condition(
            checks,
            "Get work type",
            work_type_get.status == 200 and _check_item(work_type_get, work_type_id),
            f"HTTP {work_type_get.status}; returned expected record"
            if work_type_get.status == 200 and _check_item(work_type_get, work_type_id)
            else f"HTTP {work_type_get.status}; expected created record",
        )
        check_status(
            checks,
            "Update work type",
            request(
                "PATCH",
                f"/api/v1/work-types/{work_type_id}",
                bearer=operator_token,
                payload={"name": "Reference test work type updated"},
            ),
            200,
        )
        check_status(
            checks,
            "Duplicate work type code returns 409",
            request(
                "POST",
                "/api/v1/work-types",
                bearer=operator_token,
                payload={
                    "code": work_type_code,
                    "name": "Duplicate work type",
                    "unit_type": "locomotive",
                },
            ),
            409,
        )

        subtask_response = request(
            "POST",
            f"/api/v1/work-types/{work_type_id}/subtasks",
            bearer=operator_token,
            payload={"name": "Reference test subtask", "sort_order": 1},
        )
        subtask_id = _record_created(
            checks,
            resources,
            "Create work subtask",
            subtask_response,
            f"/api/v1/work-types/{work_type_id}/subtasks",
        )
        check_status(
            checks,
            "List work subtasks",
            request(
                "GET",
                f"/api/v1/work-types/{work_type_id}/subtasks",
                bearer=operator_token,
            ),
            200,
        )
        check_status(
            checks,
            "Get work subtask",
            request(
                "GET",
                f"/api/v1/work-types/{work_type_id}/subtasks/{subtask_id}",
                bearer=operator_token,
            ),
            200,
        )
        check_status(
            checks,
            "Update work subtask",
            request(
                "PATCH",
                f"/api/v1/work-types/{work_type_id}/subtasks/{subtask_id}",
                bearer=operator_token,
                payload={"name": "Reference test subtask updated"},
            ),
            200,
        )
        check_status(
            checks,
            "Referenced work type delete returns 409",
            request(
                "DELETE",
                f"/api/v1/work-types/{work_type_id}",
                bearer=operator_token,
            ),
            409,
        )

        template_response = request(
            "POST",
            "/api/v1/work-type-templates",
            bearer=operator_token,
            payload={
                "work_type_id": work_type_id,
                "department_id": department_id,
                "nomenclature_id": None,
                "name": "Reference template item",
                "inv_no": f"REF-{suffix[:8]}",
                "unit": "шт.",
                "default_quantity": 1,
                "is_required": False,
                "note": None,
            },
        )
        template_id = _record_created(
            checks,
            resources,
            "Create work type template",
            template_response,
            "/api/v1/work-type-templates",
        )
        check_status(
            checks,
            "List work type templates",
            request(
                "GET",
                f"/api/v1/work-type-templates?work_type={work_type_code}&department_id={department_id}",
                bearer=operator_token,
            ),
            200,
        )
        check_status(
            checks,
            "Get work type template",
            request(
                "GET",
                f"/api/v1/work-type-templates/{template_id}",
                bearer=operator_token,
            ),
            200,
        )
        check_status(
            checks,
            "Update work type template",
            request(
                "PATCH",
                f"/api/v1/work-type-templates/{template_id}",
                bearer=operator_token,
                payload={"default_quantity": 2},
            ),
            200,
        )

        interval_code = f"REF-{suffix[:10]}"
        interval_response = request(
            "POST",
            "/api/v1/maintenance-intervals",
            bearer=operator_token,
            payload={
                "work_type_id": work_type_id,
                "code": interval_code,
                "name": "Reference test interval",
                "interval_km": 1234.5,
                "interval_days": 30,
                "asset_types": ["locomotive"],
                "warn_percent": 10,
                "is_active": True,
            },
        )
        interval_id = _record_created(
            checks,
            resources,
            "Create maintenance interval",
            interval_response,
            "/api/v1/maintenance-intervals",
        )
        check_status(
            checks,
            "List maintenance intervals",
            request(
                "GET",
                "/api/v1/maintenance-intervals?limit=1000",
                bearer=operator_token,
            ),
            200,
        )
        check_status(
            checks,
            "Get maintenance interval",
            request(
                "GET",
                f"/api/v1/maintenance-intervals/{interval_id}",
                bearer=operator_token,
            ),
            200,
        )
        check_status(
            checks,
            "Update maintenance interval",
            request(
                "PATCH",
                f"/api/v1/maintenance-intervals/{interval_id}",
                bearer=operator_token,
                payload={"interval_days": 45},
            ),
            200,
        )
        check_status(
            checks,
            "Duplicate maintenance interval code returns 409",
            request(
                "POST",
                "/api/v1/maintenance-intervals",
                bearer=operator_token,
                payload={
                    "code": interval_code,
                    "name": "Duplicate test interval",
                    "interval_days": 20,
                },
            ),
            409,
        )
        check_status(
            checks,
            "Delete maintenance interval",
            request(
                "DELETE",
                f"/api/v1/maintenance-intervals/{interval_id}",
                bearer=operator_token,
            ),
            204,
        )
        resources.remove(("/api/v1/maintenance-intervals", interval_id))

        check_status(
            checks,
            "Delete work type template",
            request(
                "DELETE",
                f"/api/v1/work-type-templates/{template_id}",
                bearer=operator_token,
            ),
            204,
        )
        resources.remove(("/api/v1/work-type-templates", template_id))
        check_status(
            checks,
            "Delete work subtask",
            request(
                "DELETE",
                f"/api/v1/work-types/{work_type_id}/subtasks/{subtask_id}",
                bearer=operator_token,
            ),
            204,
        )
        resources.remove(
            (f"/api/v1/work-types/{work_type_id}/subtasks", subtask_id)
        )
        check_status(
            checks,
            "Delete work type",
            request(
                "DELETE",
                f"/api/v1/work-types/{work_type_id}",
                bearer=operator_token,
            ),
            204,
        )
        resources.remove(("/api/v1/work-types", work_type_id))

        operator_write = request(
            "POST",
            "/api/v1/departments",
            bearer=operator_token,
            payload={"name": f"Reference operator write {suffix}", "color": "#111111"},
        )
        _record_created(
            checks,
            resources,
            "Operator is authorized to write",
            operator_write,
            "/api/v1/departments",
        )

    except SmokeError as exc:
        stopped_reason = str(exc)
    finally:
        if admin_token is not None:
            for index, (user_id, is_master) in enumerate(users, start=1):
                cleanup_payload: dict[str, Any] = {"is_active": False}
                if is_master:
                    cleanup_payload.update({"role": "operator", "section_id": None})
                response = request(
                    "PATCH",
                    f"/api/v1/users/{user_id}",
                    bearer=admin_token,
                    payload=cleanup_payload,
                )
                check_status(checks, f"Cleanup: deactivate test user {index}", response, 200)

            for endpoint, record_id in reversed(resources):
                response = request(
                    "DELETE",
                    f"{endpoint}/{record_id}",
                    bearer=admin_token,
                )
                cleanup_ok = response.status in {204, 404}
                check_condition(
                    checks,
                    f"Cleanup: {endpoint.rsplit('/', 1)[-1]}",
                    cleanup_ok,
                    f"HTTP {response.status}"
                    if cleanup_ok
                    else f"HTTP {response.status}; test data remains referenced",
                )

    if stopped_reason:
        print(f"\nReference test stopped: {stopped_reason}")
    print_results(checks)
    return 1 if stopped_reason or any(not item.passed for item in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
