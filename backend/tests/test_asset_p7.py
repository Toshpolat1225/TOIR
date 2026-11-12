import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.core.permissions import ROLE_DEFAULTS, ROLE_DENIED, require_permission
from app.models.asset_field_changes import AssetFieldChange
from app.routers import assets as assets_router
from app.schemas.assets import (
    FixedAssetInventoryImportApply,
    FixedAssetInventoryImportRequest,
)
from app.services import asset_inventory_import
from app.services import unified_assets
from source_check_utils import without_locale_block


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "backend" / "alembic" / "versions" / "0020_p7_permission_grants.py"
LANGUAGE_FILES = (
    MIGRATION,
    ROOT / "backend" / "app" / "schemas" / "assets.py",
    ROOT / "backend" / "app" / "schemas" / "wialon.py",
    ROOT / "backend" / "app" / "repositories" / "assets.py",
    ROOT / "backend" / "app" / "repositories" / "unified_assets.py",
    ROOT / "backend" / "app" / "services" / "asset_inventory_import.py",
    ROOT / "backend" / "app" / "services" / "unified_assets.py",
    ROOT / "backend" / "app" / "routers" / "assets.py",
    ROOT / "backend" / "scripts" / "e2e_asset_inventory_import.py",
    Path(__file__),
    ROOT / "app" / "dashboard" / "directories" / "assets" / "page.tsx",
    ROOT / "lib" / "api.ts",
)


class ScalarRows:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


def _asset(asset_id, *, name="ПЭ-2М 101", inv_number="WIALON-101", accounting=None):
    return SimpleNamespace(
        id=asset_id,
        name=name,
        inv_number=inv_number,
        accounting_inv_number=accounting,
        inv_number_is_provisional=True,
        updated_at=None,
    )


@pytest.mark.asyncio
async def test_inventory_preview_is_read_only_and_normalizes_name(monkeypatch):
    asset_id = uuid4()
    asset = _asset(asset_id)
    db = SimpleNamespace(add=Mock(), commit=AsyncMock())
    monkeypatch.setattr(
        asset_inventory_import.repository,
        "list_asset_names",
        AsyncMock(return_value=[(asset_id, asset.name)]),
    )
    monkeypatch.setattr(
        asset_inventory_import.repository,
        "get_asset",
        AsyncMock(return_value=asset),
    )
    monkeypatch.setattr(
        asset_inventory_import.repository,
        "find_inventory_records",
        AsyncMock(return_value=[]),
    )

    result = await asset_inventory_import.preview_inventory_import(
        db,
        FixedAssetInventoryImportRequest(
            csv_text="name,inv_number,accounting_inv_number\r\n"
            "PE 2M 101,INV-101,ACC-101\r\n"
        ),
    )

    assert result.items[0].status == "ok"
    assert result.items[0].asset_id == asset_id
    assert result.items[0].accounting_inv_number == "ACC-101"
    assert db.add.call_count == 0
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_inventory_preview_reports_ambiguous_missing_duplicate_and_empty(
    monkeypatch,
):
    first_id, second_id = uuid4(), uuid4()
    monkeypatch.setattr(
        asset_inventory_import.repository,
        "list_asset_names",
        AsyncMock(
            return_value=[
                (first_id, "Локомотив 101"),
                (second_id, "Локомотив 101"),
            ]
        ),
    )
    monkeypatch.setattr(
        asset_inventory_import.repository,
        "get_asset",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        asset_inventory_import.repository,
        "find_inventory_records",
        AsyncMock(return_value=[]),
    )
    result = await asset_inventory_import.preview_inventory_import(
        SimpleNamespace(),
        FixedAssetInventoryImportRequest(
            rows=[
                {"name": "Локомотив 101", "inv_number": "INV-1"},
                {"asset_id": str(uuid4()), "inv_number": "INV-2"},
                {"asset_id": str(first_id), "inv_number": "INV-3"},
                {},
            ]
        ),
    )
    assert [item.status for item in result.items] == [
        "ambiguous",
        "not_found",
        "not_found",
        "empty",
    ]


@pytest.mark.asyncio
async def test_inventory_preview_marks_database_and_file_duplicates(monkeypatch):
    first_id, second_id = uuid4(), uuid4()
    assets = {
        first_id: _asset(first_id, name="Asset one"),
        second_id: _asset(second_id, name="Asset two"),
    }
    monkeypatch.setattr(
        asset_inventory_import.repository,
        "list_asset_names",
        AsyncMock(return_value=[(first_id, "Asset one"), (second_id, "Asset two")]),
    )
    monkeypatch.setattr(
        asset_inventory_import.repository,
        "get_asset",
        AsyncMock(side_effect=lambda db, asset_id: assets.get(asset_id)),
    )
    monkeypatch.setattr(
        asset_inventory_import.repository,
        "find_inventory_records",
        AsyncMock(return_value=[(uuid4(), "USED-3", None)]),
    )
    result = await asset_inventory_import.preview_inventory_import(
        SimpleNamespace(),
        FixedAssetInventoryImportRequest(
            rows=[
                {"asset_id": str(first_id), "inv_number": "FILE-DUP"},
                {"asset_id": str(second_id), "inv_number": "FILE-DUP"},
                {"asset_id": str(first_id), "inv_number": "USED-3"},
            ]
        ),
    )
    assert [item.status for item in result.items] == [
        "duplicate",
        "duplicate",
        "duplicate",
    ]


@pytest.mark.asyncio
async def test_inventory_apply_updates_fields_clears_provisional_and_journals(monkeypatch):
    asset_id = uuid4()
    asset = _asset(asset_id)
    db = SimpleNamespace(
        add=Mock(),
        flush=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    monkeypatch.setattr(
        asset_inventory_import.repository,
        "get_assets_for_update",
        AsyncMock(return_value=[asset]),
    )
    monkeypatch.setattr(
        asset_inventory_import.repository,
        "find_inventory_records",
        AsyncMock(return_value=[]),
    )

    updated = await asset_inventory_import.apply_inventory_import(
        db,
        FixedAssetInventoryImportApply(
            rows=[
                {
                    "asset_id": str(asset_id),
                    "inv_number": "REAL-101",
                    "accounting_inv_number": "ACC-101",
                }
            ]
        ),
    )

    assert updated == 1
    assert asset.inv_number == "REAL-101"
    assert asset.accounting_inv_number == "ACC-101"
    assert asset.inv_number_is_provisional is False
    changes = [call.args[0] for call in db.add.call_args_list]
    assert any(
        isinstance(change, AssetFieldChange)
        and change.field == "inv_number"
        and change.kind == "manual"
        for change in changes
    )
    assert any(
        isinstance(change, AssetFieldChange)
        and change.field == "inv_number_is_provisional"
        and change.kind == "manual"
        for change in changes
    )
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_inventory_apply_rolls_back_on_atomic_integrity_error(monkeypatch):
    asset_id = uuid4()
    asset = _asset(asset_id)
    db = SimpleNamespace(
        add=Mock(),
        flush=AsyncMock(),
        commit=AsyncMock(side_effect=IntegrityError(None, None, Exception())),
        rollback=AsyncMock(),
    )
    monkeypatch.setattr(
        asset_inventory_import.repository,
        "get_assets_for_update",
        AsyncMock(return_value=[asset]),
    )
    monkeypatch.setattr(
        asset_inventory_import.repository,
        "find_inventory_records",
        AsyncMock(return_value=[]),
    )

    with pytest.raises(HTTPException) as error:
        await asset_inventory_import.apply_inventory_import(
            db,
            FixedAssetInventoryImportApply(
                rows=[{"asset_id": str(asset_id), "inv_number": "REAL-101"}]
            ),
        )
    assert error.value.status_code == 409
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_inventory_apply_rejects_repeated_numbers_before_writing():
    db = SimpleNamespace(add=Mock(), rollback=AsyncMock())
    with pytest.raises(HTTPException) as error:
        await asset_inventory_import.apply_inventory_import(
            db,
            FixedAssetInventoryImportApply(
                rows=[
                    {"asset_id": str(uuid4()), "inv_number": "DUP-1"},
                    {"asset_id": str(uuid4()), "inv_number": "DUP-1"},
                ]
            ),
        )
    assert error.value.status_code == 409
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_permission_matrix_and_endpoints_deny_master_and_management_writes():
    expected = {
        "admin": (True, True, True),
        "operator": (True, True, True),
        "management": (True, False, False),
        "master": (False, False, False),
    }
    codes = (
        "asset_links.view",
        "asset_links.manage",
        "asset_conflicts.manage",
    )
    for role, grants in expected.items():
        for code, granted in zip(codes, grants):
            user = SimpleNamespace(role=role)
            db = SimpleNamespace(
                execute=AsyncMock(return_value=ScalarRows(granted))
            )
            dependency = require_permission(code)
            if granted:
                assert await dependency(user, db) is user
            else:
                with pytest.raises(HTTPException) as error:
                    await dependency(user, db)
                assert error.value.status_code == 403

    for role in ("master", "management"):
        with pytest.raises(HTTPException) as error:
            assets_router._require_asset_operator(SimpleNamespace(role=role))
        assert error.value.status_code == 403
        with pytest.raises(HTTPException) as error:
            await assets_router.preview_inventory_import(
                FixedAssetInventoryImportRequest(
                    rows=[{"asset_id": str(uuid4()), "inv_number": "INV-1"}]
                ),
                SimpleNamespace(role=role),
                SimpleNamespace(),
            )
        assert error.value.status_code == 403
        with pytest.raises(HTTPException) as error:
            await assets_router.apply_inventory_import(
                FixedAssetInventoryImportApply(
                    rows=[{"asset_id": str(uuid4()), "inv_number": "INV-1"}]
                ),
                SimpleNamespace(role=role),
                SimpleNamespace(),
            )
        assert error.value.status_code == 403
        with pytest.raises(HTTPException) as error:
            await assets_router.post_bulk_org_unit_update(
                SimpleNamespace(asset_ids=[uuid4()], org_unit_id=uuid4()),
                SimpleNamespace(role=role),
                SimpleNamespace(),
            )
        assert error.value.status_code == 403


def test_p7_permission_migration_reconciles_all_role_values():
    codes = {
        "asset_links.view",
        "asset_links.manage",
        "asset_conflicts.manage",
    }
    assert codes <= ROLE_DEFAULTS["admin"]
    assert codes <= ROLE_DEFAULTS["operator"]
    assert ROLE_DEFAULTS["management"].intersection(codes) == {"asset_links.view"}
    assert ROLE_DEFAULTS["master"].isdisjoint(codes)
    assert codes <= ROLE_DENIED["master"]
    assert "asset_conflicts.manage" in ROLE_DENIED["management"]
    assert "asset_links.manage" not in ROLE_DEFAULTS["management"]
    source = MIGRATION.read_text(encoding="utf-8")
    ast.parse(source)
    assert 'revision = "0020_p7_permission_grants"' in source
    assert 'down_revision = "0019_asset_field_changes"' in source
    assert "ON CONFLICT (role, permission_code)" in source
    assert "DO UPDATE SET granted = EXCLUDED.granted" in source
    assert "('master', 'asset_links.view', false)" in source
    assert "('management', 'asset_links.view', true)" in source
    assert "('management', 'asset_links.manage', false)" in source
    assert "('management', 'asset_conflicts.manage', false)" in source
    ast.parse(
        (ROOT / "backend" / "scripts" / "e2e_asset_inventory_import.py").read_text(
            encoding="utf-8"
        )
    )
    paths = {route.path for route in assets_router.router.routes}
    assert "/fixed-assets/inv-import/preview" in paths
    assert "/fixed-assets/inv-import/apply" in paths


@pytest.mark.asyncio
async def test_unified_assets_can_filter_missing_organizational_unit(monkeypatch):
    mocked = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(unified_assets.repository, "list_unified_assets", mocked)
    result, total = await unified_assets.list_unified_assets(
        SimpleNamespace(),
        source=None,
        asset_type=None,
        asset_status=None,
        section_id=None,
        without_org_unit=True,
        master_section_id=None,
        q=None,
        limit=50,
        offset=0,
        sort_by="name",
        sort_order="asc",
    )
    assert result == []
    assert total == 0
    assert mocked.await_args.kwargs["without_org_unit"] is True


def test_p7_ui_and_api_files_do_not_contain_foreign_alphabet_characters():
    forbidden = set(map(chr, (0x04AF, 0x04E9, 0x04AE, 0x04E8, 0x049B, 0x0493, 0x04B3, 0x045E)))
    for path in LANGUAGE_FILES:
        text = path.read_text(encoding="utf-8")
        if path.name == "page.tsx" and path.parent.name == "assets":
            text = without_locale_block(text, "uz-Cyrl")
        assert not forbidden.intersection(text), str(path.relative_to(ROOT))


def test_next_config_does_not_ignore_build_or_typescript_errors():
    config = (ROOT / "next.config.mjs").read_text(encoding="utf-8")
    assert "ignoreBuildErrors" not in config
    assert "ignoreDuringBuilds" not in config
