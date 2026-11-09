from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers import assets as assets_router
from app.schemas.assets import FixedAssetCreate, FixedAssetUpdate
from app.services import assets as assets_service


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_org_unit_patch_is_persisted_audited_and_read_back():
    asset_id, org_unit_id = uuid4(), uuid4()
    asset = SimpleNamespace(
        id=asset_id,
        org_unit_id=None,
        gtk_id=None,
        wialon_id=None,
        asset_type="wagon",
        model_id=None,
        number=None,
        number_normalized=None,
        inv_number="ASSET-1",
        inv_number_is_provisional=False,
        updated_at=None,
        section_id=None,
        mileage=None,
        name="Wagon 1",
    )
    db = SimpleNamespace(add=Mock(), refresh=AsyncMock())
    with (
        patch.object(
            assets_service,
            "_get_scoped_asset",
            new=AsyncMock(return_value=asset),
        ),
        patch.object(
            assets_service.references_repository,
            "get_non_archived_section",
            new=AsyncMock(return_value=SimpleNamespace(id=org_unit_id)),
        ),
        patch.object(
            assets_service.asset_links_repository,
            "get_active",
            new=AsyncMock(return_value=[]),
        ),
        patch.object(assets_service, "_commit", new=AsyncMock()) as commit,
        patch.object(assets_service.repository, "enrich_asset_display_data", new=AsyncMock()),
        patch.object(assets_service, "asset_read", side_effect=lambda value: value),
    ):
        response = await assets_service.update_fixed_asset(
            db, asset_id, FixedAssetUpdate(org_unit_id=org_unit_id)
        )

    assert response.section_id == org_unit_id
    assert asset.section_id == org_unit_id
    journal = db.add.call_args.args[0]
    assert (journal.field, journal.old_value, journal.new_value) == (
        "org_unit_id",
        None,
        str(org_unit_id),
    )
    commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_unrelated_patch_does_not_clear_org_unit():
    asset_id, org_unit_id = uuid4(), uuid4()
    asset = SimpleNamespace(
        id=asset_id,
        org_unit_id=org_unit_id,
        gtk_id=None,
        wialon_id=None,
        asset_type="wagon",
        model_id=None,
        number=None,
        number_normalized=None,
        inv_number="ASSET-1",
        inv_number_is_provisional=False,
        updated_at=None,
        section_id=None,
        mileage=None,
        name="Wagon 1",
    )
    db = SimpleNamespace(add=Mock(), refresh=AsyncMock())
    with (
        patch.object(
            assets_service,
            "_get_scoped_asset",
            new=AsyncMock(return_value=asset),
        ),
        patch.object(
            assets_service.asset_links_repository,
            "get_active",
            new=AsyncMock(return_value=[]),
        ),
        patch.object(assets_service, "_commit", new=AsyncMock()),
        patch.object(assets_service.repository, "enrich_asset_display_data", new=AsyncMock()),
        patch.object(assets_service, "asset_read", side_effect=lambda value: value),
    ):
        response = await assets_service.update_fixed_asset(
            db, asset_id, FixedAssetUpdate(inv_number="ASSET-2")
        )

    assert response.org_unit_id == org_unit_id
    assert not any(
        getattr(call.args[0], "field", None) == "org_unit_id"
        for call in db.add.call_args_list
    )


@pytest.mark.asyncio
async def test_org_unit_patch_rejects_unavailable_section_with_422():
    asset = SimpleNamespace(
        id=uuid4(),
        org_unit_id=None,
        gtk_id=None,
        wialon_id=None,
        asset_type="wagon",
        model_id=None,
        number=None,
        number_normalized=None,
        inv_number="ASSET-1",
        inv_number_is_provisional=False,
        updated_at=None,
        section_id=None,
        mileage=None,
    )
    with (
        patch.object(
            assets_service,
            "_get_scoped_asset",
            new=AsyncMock(return_value=asset),
        ),
        patch.object(
            assets_service.references_repository,
            "get_non_archived_section",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            assets_service.asset_links_repository,
            "get_active",
            new=AsyncMock(return_value=[]),
        ),
    ):
        with pytest.raises(HTTPException) as error:
            await assets_service.update_fixed_asset(
                SimpleNamespace(),
                asset.id,
                FixedAssetUpdate(org_unit_id=uuid4()),
            )
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_create_preserves_org_unit_and_journals_passport_fields():
    org_unit_id = uuid4()
    db = SimpleNamespace(
        add=Mock(),
        flush=AsyncMock(),
        refresh=AsyncMock(),
    )
    created = []
    with (
        patch.object(assets_service, "_validate_gtk_link", new=AsyncMock()),
        patch.object(
            assets_service.references_repository,
            "get_non_archived_section",
            new=AsyncMock(return_value=SimpleNamespace(id=org_unit_id)),
        ),
        patch.object(
            assets_service.repository,
            "active_catalog_value_exists",
            new=AsyncMock(return_value=True),
        ),
        patch.object(
            assets_service.asset_passport,
            "prepare_new_asset",
            new=AsyncMock(
                return_value={
                    "number": None,
                    "number_normalized": None,
                    "model_id": None,
                    "name": "Wagon 1",
                }
            ),
        ),
        patch.object(
            assets_service.repository,
            "add_asset",
            new=AsyncMock(side_effect=lambda db, asset: created.append(asset)),
        ),
        patch.object(assets_service, "_commit", new=AsyncMock()) as commit,
        patch.object(assets_service.repository, "enrich_asset_display_data", new=AsyncMock()),
        patch.object(
            assets_service,
            "asset_read",
            side_effect=lambda asset: asset,
        ),
    ):
        payload = FixedAssetCreate(
            inv_number="INV-1",
            name="Wagon 1",
            asset_type="wagon",
            org_unit_id=org_unit_id,
        )
        response = await assets_service.create_fixed_asset(db, payload)

    assert response.org_unit_id == org_unit_id
    assert created[0].org_unit_id == org_unit_id
    assert any(
        getattr(call.args[0], "field", None) == "org_unit_id"
        for call in db.add.call_args_list
    )
    commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_removes_unreferenced_asset_and_commits():
    asset = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(delete=AsyncMock())
    with (
        patch.object(
            assets_service.repository,
            "get_asset",
            new=AsyncMock(return_value=asset),
        ),
        patch.object(
            assets_service.repository,
            "count_asset_references",
            new=AsyncMock(return_value=0),
        ),
        patch.object(assets_service, "_commit", new=AsyncMock()) as commit,
    ):
        await assets_service.delete_fixed_asset(db, asset.id)
    db.delete.assert_awaited_once_with(asset)
    commit.assert_awaited_once()


def test_fixed_asset_api_methods_are_in_fixed_assets_client():
    source = (ROOT / "lib" / "api.ts").read_text(encoding="utf-8")
    fixed_assets_source = source.split("const fixedAssets = {", 1)[1].split(
        "\n};",
        1,
    )[0]
    gtk_source = source.split("const gtk = {", 1)[1].split("\n};", 1)[0]
    for method in (
        "previewInventoryImport",
        "applyInventoryImport",
        "bulkUpdateOrgUnit",
        "create",
        "update",
        "remove",
    ):
        assert f"async {method}(" in fixed_assets_source
    assert "previewInventoryImport" not in gtk_source
    assert "applyInventoryImport" not in gtk_source
    assert 'path: "/fixed-assets/inv-import/preview"' in fixed_assets_source
    assert 'path: "/fixed-assets/inv-import/apply"' in fixed_assets_source
    assert 'path: "/fixed-assets/bulk-org-unit"' in fixed_assets_source


def test_os_page_routes_all_api_calls_through_known_api_methods():
    source = (ROOT / "app" / "dashboard" / "os" / "page.tsx").read_text(
        encoding="utf-8"
    )
    assert "api.fixedAssets.previewInventoryImport" in source
    assert "api.fixedAssets.applyInventoryImport" in source
    assert "api.fixedAssets.update" in source
    assert "api.fixedAssets.create" in source
    assert "api.fixedAssets.remove" in source
    to_row = source.split("function toRow(", 1)[1].split("\n}", 1)[0]
    assert "org_unit_id:  a.orgUnitId" in to_row


def test_root_layout_does_not_mount_vercel_analytics():
    source = (ROOT / "app" / "layout.tsx").read_text(encoding="utf-8")
    assert "@vercel/analytics/next" not in source
    assert "<Analytics" not in source
