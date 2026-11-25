"""Who may see and change the migration journal (no database needed)."""
from app.core.permissions import PERMISSIONS, ROLE_DEFAULTS, ROLE_DENIED


def test_permissions_exist_and_follow_the_agreed_role_matrix():
    for code in ("data_migration.view", "data_migration.manage"):
        assert code in PERMISSIONS
    assert {"data_migration.view", "data_migration.manage"} <= ROLE_DEFAULTS["admin"]
    assert {"data_migration.view", "data_migration.manage"} <= ROLE_DEFAULTS["operator"]
    assert "data_migration.view" in ROLE_DEFAULTS["management"] and "data_migration.manage" not in ROLE_DEFAULTS["management"]
    assert not {"data_migration.view", "data_migration.manage"} & ROLE_DEFAULTS["master"]


def test_denied_roles_cannot_be_granted_these_by_the_matrix():
    assert {"data_migration.view", "data_migration.manage"} <= ROLE_DENIED["master"]
    assert "data_migration.manage" in ROLE_DENIED["management"]


def test_routes_are_registered_behind_the_right_permissions():
    from app.main import app

    routes = {(m, r.path): r for r in app.routes if hasattr(r, "methods") for m in r.methods if "data-migrations" in r.path}
    assert ("GET", "/api/v1/data-migrations") in routes
    assert ("PATCH", "/api/v1/data-migrations/items/{item_id}") in routes
    assert ("DELETE", "/api/v1/data-migrations/items/{item_id}") in routes
    assert ("POST", "/api/v1/data-migrations/{batch_id}/revert") in routes
    manage = routes[("DELETE", "/api/v1/data-migrations/items/{item_id}")]
    names = " ".join(str(d.call.__qualname__) for d in manage.dependant.dependencies)
    assert "dependency" in names


def test_the_edit_body_refuses_unknown_fields():
    import pytest
    from pydantic import ValidationError

    from app.schemas.data_migration import DataMigrationItemUpdate

    DataMigrationItemUpdate(new_value="2026-01-01")
    with pytest.raises(ValidationError):
        DataMigrationItemUpdate(new_value="2026-01-01", asset_id="x")


def test_the_manifest_keeps_cyrillic_names_out_of_the_command_line(tmp_path):
    import json

    import pytest

    from app.services.data_migration_import import load_manifest

    good = tmp_path / "m.json"
    good.write_text(json.dumps([{"file": "a.csv", "name": "ЖДЦ-1: ПТОВ", "source_file": "ЖДЦ-1 ПТОВ готов.xlsx"}], ensure_ascii=False), encoding="utf-8")
    [job] = load_manifest(str(good))
    assert job["name"] == "ЖДЦ-1: ПТОВ" and job["field"] == "last_maint_date" and job["file"] == str(tmp_path / "a.csv")
    bad = tmp_path / "b.json"
    bad.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_manifest(str(bad))
    bad.write_text(json.dumps([{"file": "a.csv", "name": "x"}]), encoding="utf-8")
    with pytest.raises(ValueError):
        load_manifest(str(bad))
