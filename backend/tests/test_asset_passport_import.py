import ast
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.models.assets import FixedAsset
from app.schemas.asset_data_import import (
    FixedAssetsPassportImportApplyRequest,
    FixedAssetsPassportImportRequest,
)
from app.services import asset_passport_import as importer
from app.services import asset_passport

ROOT = Path(__file__).resolve().parents[2]
LANGUAGE_FILES = (
    ROOT / "backend" / "app" / "schemas" / "asset_data_import.py",
    ROOT / "backend" / "app" / "services" / "asset_passport_import.py",
    ROOT / "backend" / "app" / "routers" / "assets.py",
    Path(__file__),
    ROOT / "app" / "dashboard" / "os" / "page.tsx",
    ROOT / "lib" / "api.ts",
)


def _document(*, asset_type="вагон-самосвал", inv_number="INV-1", links=None):
    return {
        "assets": [
            {
                "asset_type": asset_type,
                "model": "18-100",
                "serial_number": "SN-004",
                "inv_number": inv_number,
                "section": "ЖДЦ-1",
                "year_built": 2020,
                "commissioned_at": "2021-01-02T00:00:00",
                "decommissioned_at": None,
                "links": links or {"wialon_id": None, "gtk_id": None},
            }
        ]
    }


async def _sections(db):
    return [SimpleNamespace(id=uuid4(), name="ЖДЦ-1")]


@pytest.mark.asyncio
async def test_preview_maps_all_json_types_and_does_not_write(monkeypatch):
    monkeypatch.setattr(importer.assets_repository, "list_active_sections", _sections)
    monkeypatch.setattr(
        importer.assets_repository, "count_fixed_assets", AsyncMock(return_value=86)
    )
    db = SimpleNamespace(add=Mock(), commit=AsyncMock())
    source_types = {
        "вагон-самосвал": "wagon",
        "тяговой   агрегат": "locomotive",
        "цистерна": "tank_car",
        "платформа": "platform",
        "тепловоз": "diesel",
        "специальный самоходный подвижной состав": "special_self_propelled",
    }

    for source_type, expected in source_types.items():
        preview = await importer.preview(
            db,
            FixedAssetsPassportImportRequest(
                json_text=json.dumps(_document(asset_type=source_type))
            ),
        )
        assert preview.ready == 1
        assert preview.items[0].asset_type == expected

    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_preview_reports_inventory_and_serial_duplicates_as_allowed(monkeypatch):
    monkeypatch.setattr(importer.assets_repository, "list_active_sections", _sections)
    monkeypatch.setattr(
        importer.assets_repository, "count_fixed_assets", AsyncMock(return_value=0)
    )
    first = _document()["assets"][0]
    second = {**first, "serial_number": "SN004"}
    document = {"assets": [first, second]}

    preview = await importer.preview(
        SimpleNamespace(),
        FixedAssetsPassportImportRequest(json_text=json.dumps(document)),
    )

    assert preview.ready == 2
    assert preview.blocked == 0
    assert preview.duplicate_inventory_groups == 1
    assert preview.duplicate_number_groups == 1
    assert all(row.status == "duplicate" for row in preview.items)
    assert all(row.wialon_id is None and row.gtk_id is None for row in preview.items)


@pytest.mark.asyncio
async def test_preview_blocks_repeated_external_ids(monkeypatch):
    monkeypatch.setattr(importer.assets_repository, "list_active_sections", _sections)
    monkeypatch.setattr(
        importer.assets_repository, "count_fixed_assets", AsyncMock(return_value=0)
    )
    first = _document(links={"wialon_id": "W-1", "gtk_id": None})["assets"][0]
    second = {
        **first,
        "inv_number": "INV-2",
        "links": {"wialon_id": "W-1", "gtk_id": None},
    }
    preview = await importer.preview(
        SimpleNamespace(),
        FixedAssetsPassportImportRequest(
            json_text=json.dumps({"assets": [first, second]})
        ),
    )

    assert preview.ready == 0
    assert preview.blocked == 2
    assert all(row.status == "invalid" for row in preview.items)


@pytest.mark.asyncio
async def test_apply_accepts_number_duplicates_and_imports_every_row(monkeypatch):
    section_id = uuid4()
    monkeypatch.setattr(
        importer.assets_repository,
        "list_active_sections",
        AsyncMock(return_value=[SimpleNamespace(id=section_id, name="ЖДЦ-1")]),
    )
    delete_assets = AsyncMock(return_value=1)
    monkeypatch.setattr(importer, "_delete_asset_rows", delete_assets)
    model_id = uuid4()
    monkeypatch.setattr(
        importer.asset_models_repository,
        "add_if_missing",
        AsyncMock(return_value=SimpleNamespace(id=model_id, asset_type="wagon")),
    )
    monkeypatch.setattr(importer.asset_links_service, "link", AsyncMock())
    monkeypatch.setattr(importer.asset_field_changes, "record_changes", Mock())
    added = []

    async def flush():
        for item in added:
            if isinstance(item, FixedAsset) and item.id is None:
                item.id = uuid4()

    db = SimpleNamespace(
        execute=AsyncMock(),
        add=Mock(side_effect=added.append),
        flush=AsyncMock(side_effect=flush),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    first = _document()["assets"][0]
    second = {**first, "serial_number": "SN004"}
    document = {"assets": [first, second]}

    result = await importer.apply(
        db,
        FixedAssetsPassportImportApplyRequest(
            json_text=json.dumps(document),
            source_hash=importer._source_hash(document),
        ),
    )

    imported = [item for item in added if isinstance(item, FixedAsset)]
    assert result.imported_count == 2
    assert [asset.number for asset in imported] == ["SN-004", "SN004"]
    assert all(asset.number == asset.serial_number for asset in imported)
    delete_assets.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_rejects_invalid_rows_before_deleting_assets(monkeypatch):
    monkeypatch.setattr(importer.assets_repository, "list_active_sections", _sections)
    delete_assets = AsyncMock(return_value=1)
    monkeypatch.setattr(importer, "_delete_asset_rows", delete_assets)
    document = _document(asset_type="unknown")
    db = SimpleNamespace(
        execute=AsyncMock(),
        add=Mock(),
        flush=AsyncMock(),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )

    with pytest.raises(HTTPException) as error:
        await importer.apply(
            db,
            FixedAssetsPassportImportApplyRequest(
                json_text=json.dumps(document),
                source_hash=importer._source_hash(document),
            ),
        )

    assert error.value.status_code == 409
    delete_assets.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_preview_blocks_same_normalized_model_used_by_different_types(monkeypatch):
    monkeypatch.setattr(importer.assets_repository, "list_active_sections", _sections)
    monkeypatch.setattr(
        importer.assets_repository, "count_fixed_assets", AsyncMock(return_value=0)
    )
    first = _document(asset_type="цистерна")["assets"][0]
    second = {**first, "asset_type": "вагон-самосвал", "inv_number": "INV-2"}
    preview = await importer.preview(
        SimpleNamespace(),
        FixedAssetsPassportImportRequest(
            json_text=json.dumps({"assets": [first, second]})
        ),
    )

    assert preview.ready == 0
    assert all(row.status == "invalid" for row in preview.items)


@pytest.mark.asyncio
async def test_apply_replaces_without_backup_and_maps_passport_and_links(monkeypatch):
    section_id = uuid4()
    monkeypatch.setattr(
        importer.assets_repository,
        "list_active_sections",
        AsyncMock(return_value=[SimpleNamespace(id=section_id, name="ЖДЦ-1")]),
    )
    delete_graph = AsyncMock(return_value=86)
    monkeypatch.setattr(importer, "_delete_asset_rows", delete_graph)
    model_id = uuid4()
    monkeypatch.setattr(
        importer.asset_models_repository,
        "add_if_missing",
        AsyncMock(return_value=SimpleNamespace(id=model_id, asset_type="tank_car")),
    )
    link = AsyncMock()
    monkeypatch.setattr(importer.asset_links_service, "link", link)
    journal = Mock()
    monkeypatch.setattr(importer.asset_field_changes, "record_changes", journal)
    added = []

    def flush():
        for item in added:
            if isinstance(item, FixedAsset) and item.id is None:
                item.id = uuid4()

    async def async_flush():
        flush()

    db = SimpleNamespace(
        execute=AsyncMock(),
        add=Mock(side_effect=added.append),
        flush=AsyncMock(side_effect=async_flush),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    document = _document(
        asset_type="цистерна",
        links={"wialon_id": "W-100", "gtk_id": "27"},
    )
    json_text = json.dumps(document)
    source_hash = importer._source_hash(document)

    result = await importer.apply(
        db,
        FixedAssetsPassportImportApplyRequest(
            json_text=json_text, source_hash=source_hash
        ),
    )

    asset = next(item for item in added if isinstance(item, FixedAsset))
    assert result.deleted_count == 86
    assert result.imported_count == 1
    assert asset.asset_type == "tank_car"
    assert asset.number == asset.serial_number == "SN-004"
    assert asset.number_normalized == asset_passport.normalize_token("SN-004")
    assert asset.inv_number == "INV-1"
    assert asset.model_id == model_id
    assert asset.section_id == asset.org_unit_id == section_id
    assert asset.comm_date == asset.commissioned_at == date(2021, 1, 2)
    assert asset.wialon_id == "W-100"
    assert asset.gtk_id == "27"
    assert asset.inv_number_is_provisional is False
    assert [call.args[2] for call in link.await_args_list] == ["wialon", "gtk"]
    assert [call.args[3] for call in link.await_args_list] == ["W-100", "27"]
    assert all(call.kwargs["method"] == "import" for call in link.await_args_list)
    assert journal.call_count == 1
    assert not hasattr(importer, "rollback")
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_rolls_back_the_database_transaction_on_conflict(monkeypatch):
    monkeypatch.setattr(importer.assets_repository, "list_active_sections", _sections)
    monkeypatch.setattr(importer, "_delete_asset_rows", AsyncMock(return_value=1))
    monkeypatch.setattr(
        importer.asset_models_repository,
        "add_if_missing",
        AsyncMock(return_value=SimpleNamespace(id=uuid4(), asset_type="wagon")),
    )
    db = SimpleNamespace(
        execute=AsyncMock(),
        add=Mock(),
        flush=AsyncMock(side_effect=IntegrityError("insert", {}, Exception())),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    document = _document()

    with pytest.raises(HTTPException) as error:
        await importer.apply(
            db,
            FixedAssetsPassportImportApplyRequest(
                json_text=json.dumps(document),
                source_hash=importer._source_hash(document),
            ),
        )

    assert error.value.status_code == 409
    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_asset_rows_blocks_work_order_data_without_deleting_it():
    asset_id = uuid4()
    statements = []

    class Result:
        def __init__(self, *, asset_ids=(), found=False):
            self.asset_ids = asset_ids
            self.found = found

        def scalars(self):
            return SimpleNamespace(all=lambda: list(self.asset_ids))

        def first(self):
            return (True,) if self.found else None

    async def execute(statement):
        statements.append(statement)
        if getattr(statement, "is_delete", False):
            return SimpleNamespace(rowcount=1)
        table_name = statement.get_final_froms()[0].name
        if table_name == "fixed_assets":
            return Result(asset_ids=[asset_id])
        return Result(found=table_name == "work_orders")

    db = SimpleNamespace(execute=AsyncMock(side_effect=execute))

    with pytest.raises(HTTPException) as error:
        await importer._delete_asset_rows(db)

    assert error.value.status_code == 409
    assert "work_orders" in error.value.detail
    assert not any(getattr(statement, "is_delete", False) for statement in statements)


@pytest.mark.asyncio
async def test_delete_asset_rows_deletes_only_assets_when_no_blockers():
    asset_id = uuid4()
    statements = []

    class Result:
        def scalars(self):
            return SimpleNamespace(all=lambda: [asset_id])

        def first(self):
            return None

    async def execute(statement):
        statements.append(statement)
        if getattr(statement, "is_delete", False):
            return SimpleNamespace(rowcount=1)
        return Result()

    db = SimpleNamespace(execute=AsyncMock(side_effect=execute))

    assert await importer._delete_asset_rows(db) == 1
    delete_statements = [
        statement
        for statement in statements
        if getattr(statement, "is_delete", False)
    ]
    assert len(delete_statements) == 1
    assert delete_statements[0].table.name == "fixed_assets"


def test_type_migration_and_schema_have_no_backup_or_rollback_table():
    migration_path = ROOT / "backend" / "alembic" / "versions" / "0021_fixed_asset_types.py"
    duplicate_migration_path = ROOT / "backend" / "alembic" / "versions" / "0022_asset_number_dupes.py"
    migration = ast.parse(migration_path.read_text(encoding="utf-8"))
    duplicate_migration_text = duplicate_migration_path.read_text(encoding="utf-8")
    schema = (ROOT / "postgres" / "schema.sql").read_text(encoding="utf-8")
    migration_text = migration_path.read_text(encoding="utf-8")
    expected_types = ("tank_car", "platform", "special_self_propelled")

    assert 'down_revision = "0020_p7_permission_grants"' in migration_text
    assert all(f"('{asset_type}'" in migration_text for asset_type in expected_types)
    assert all(f"('{asset_type}'" in schema for asset_type in expected_types)
    assert "asset_data_import_batches" not in schema
    assert "backup" not in migration_text.lower()
    assert "op.drop_table" not in migration_text
    assert 'down_revision = "0021_fixed_asset_types"' in duplicate_migration_text
    assert "uq_fixed_assets_inv_number_real" in duplicate_migration_text
    assert "uq_fixed_assets_active_model_number" in duplicate_migration_text
    assert ast.Module(body=migration.body, type_ignores=[]).body


def test_new_import_ui_uses_russian_text_only():
    forbidden = "".join(
        chr(code) for code in (0x04AF, 0x04E9, 0x049B, 0x0493, 0x04B3, 0x045E)
    )
    for path in LANGUAGE_FILES:
        content = path.read_text(encoding="utf-8").lower()
        assert not any(character in content for character in forbidden), str(path)
