"""Repair norm routes: registered behind the existing inventory.* permissions (no database needed)."""


def test_routes_exist_and_use_the_inventory_permissions():
    from app.main import app

    routes = {(m, r.path): r for r in app.routes if hasattr(r, "methods") for m in r.methods if "repair-norms" in r.path}
    assert set(routes) == {
        ("GET", "/api/v1/repair-norms/sets"), ("GET", "/api/v1/repair-norms/items"), ("POST", "/api/v1/repair-norms/items"),
        ("PATCH", "/api/v1/repair-norms/items/{item_id}"), ("DELETE", "/api/v1/repair-norms/items/{item_id}"), ("DELETE", "/api/v1/repair-norms/sets"),
    }


def test_the_inventory_permissions_match_who_may_change_norms():
    from app.core.permissions import ROLE_DEFAULTS

    assert {"inventory.view", "inventory.create", "inventory.update", "inventory.delete"} <= ROLE_DEFAULTS["operator"]
    for role in ("master", "management"):
        assert "inventory.view" in ROLE_DEFAULTS[role]
        assert not {"inventory.create", "inventory.update", "inventory.delete"} & ROLE_DEFAULTS[role]


def test_manifest_points_the_csv_next_to_itself(tmp_path):
    import json

    import pytest

    from app.services.repair_norms import load_manifest

    m = tmp_path / "manifest.json"
    m.write_text(json.dumps([{"file": "norms/ДР_2ВС-105.csv", "work_type_code": "ДР", "asset_type": "wagon", "model_name": "2ВС-105", "source_file": "x.xls", "source_sheet": "2025"}], ensure_ascii=False), encoding="utf-8")
    [job] = load_manifest(str(m))
    assert job["file"] == str(tmp_path / "ДР_2ВС-105.csv") and job["model_name"] == "2ВС-105"
    m.write_text(json.dumps([{"file": "a.csv"}]), encoding="utf-8")
    with pytest.raises(ValueError):
        load_manifest(str(m))
