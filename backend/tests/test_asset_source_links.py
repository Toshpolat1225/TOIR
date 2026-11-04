from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.models.asset_source_links import AssetSourceLink
from app.services import asset_links


ROOT = Path(__file__).resolve().parents[2]


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


def _db_for(asset):
    return SimpleNamespace(
        execute=AsyncMock(return_value=_Result(asset)),
        rollback=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_external_id_already_active_on_another_asset_returns_409():
    asset = SimpleNamespace(id=uuid4(), asset_type="locomotive", gtk_id=None, wialon_id=None)
    other_asset = SimpleNamespace(id=uuid4())
    db = _db_for(asset)

    with (
        patch.object(asset_links.repository, "find_active", new=AsyncMock(return_value=(object(), other_asset))),
        patch.object(asset_links.repository, "get_active_for_update", new=AsyncMock()),
    ):
        with pytest.raises(HTTPException) as error:
            await asset_links.link(db, asset.id, "wialon", "unit-1", None)

    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_source_and_asset_type_mismatch_returns_422():
    asset = SimpleNamespace(id=uuid4(), asset_type="wagon", gtk_id=None, wialon_id=None)
    db = _db_for(asset)

    with pytest.raises(HTTPException) as error:
        await asset_links.link(db, asset.id, "wialon", "unit-1", None)

    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_gtk_locomotive_cannot_link_to_wagon_asset():
    asset = SimpleNamespace(id=uuid4(), asset_type="wagon", gtk_id=None, wialon_id=None)
    db = _db_for(asset)

    with patch.object(
        asset_links.gtk_repository,
        "gtk_kind",
        new=AsyncMock(return_value="locomotive"),
    ):
        with pytest.raises(HTTPException) as error:
            await asset_links.link(db, asset.id, "gtk", "55", None)

    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_database_unique_race_returns_409():
    asset = SimpleNamespace(id=uuid4(), asset_type="locomotive", gtk_id=None, wialon_id=None)
    db = _db_for(asset)
    integrity_error = IntegrityError("insert", {}, RuntimeError("unique"))

    with (
        patch.object(asset_links.repository, "find_active", new=AsyncMock(return_value=None)),
        patch.object(asset_links.repository, "get_active_for_update", new=AsyncMock(return_value=None)),
        patch.object(asset_links.repository, "add", new=AsyncMock(side_effect=integrity_error)),
    ):
        with pytest.raises(HTTPException) as error:
            await asset_links.link(db, asset.id, "wialon", "unit-1", None)

    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_unlink_ends_history_and_relink_writes_active_row_and_legacy_mirror():
    asset = SimpleNamespace(
        id=uuid4(),
        asset_type="wagon",
        gtk_id="22",
        wialon_id=None,
    )
    old_link = SimpleNamespace(
        asset_id=asset.id,
        source="gtk",
        external_id="22",
        status="active",
        unlinked_at=None,
    )
    new_link = AssetSourceLink(
        asset_id=asset.id,
        source="gtk",
        external_id="23",
        status="active",
        link_method="manual",
    )
    db = _db_for(asset)
    active_rows = [old_link]

    async def get_active_for_update(_db, asset_id, source):
        assert asset_id == asset.id
        assert source == "gtk"
        return next((row for row in active_rows if row.status == "active"), None)

    async def add_link(_db, row):
        active_rows.append(row)

    async def gtk_kind(_db, gtk_id):
        return "carriage"

    with (
        patch.object(asset_links.repository, "find_active", new=AsyncMock(return_value=None)),
        patch.object(asset_links.repository, "get_active_for_update", new=get_active_for_update),
        patch.object(asset_links.repository, "add", new=add_link),
        patch.object(asset_links.repository, "end", new=asset_links.repository.end),
        patch.object(asset_links.gtk_repository, "gtk_kind", new=gtk_kind),
    ):
        await asset_links.unlink(db, asset.id, "gtk")
        created = await asset_links.link(db, asset.id, "gtk", "23", None)

    assert old_link.status == "ended"
    assert old_link.unlinked_at is not None
    assert created.external_id == "23"
    assert created.status == "active"
    assert asset.gtk_id == "23"
    assert len(active_rows) == 2


def test_backfill_migration_is_idempotent_and_does_not_change_legacy_columns():
    migration = (
        ROOT / "backend" / "alembic" / "versions" / "0017_asset_source_links.py"
    ).read_text(encoding="utf-8")

    assert migration.count("ON CONFLICT DO NOTHING") == 2
    assert 'revision = "0017_asset_source_links"' in migration
    assert 'down_revision = "0016_gtk_mirror_cleanup"' in migration
    assert len("0017_asset_source_links") <= 32
    assert "wialon_id IS NOT NULL AND btrim(wialon_id) <> ''" in migration
    assert "gtk_id IS NOT NULL AND btrim(gtk_id) <> ''" in migration
    assert "DROP COLUMN" not in migration


def test_asset_source_links_model_and_canonical_schema_agree():
    schema = (ROOT / "postgres" / "schema.sql").read_text(encoding="utf-8")
    migration = (
        ROOT / "backend" / "alembic" / "versions" / "0017_asset_source_links.py"
    ).read_text(encoding="utf-8")
    columns = set(AssetSourceLink.__table__.columns.keys())
    table_body = schema.split("CREATE TABLE asset_source_links (", 1)[1].split(
        "\n);", 1
    )[0]
    schema_columns = {
        line.strip().split()[0]
        for line in table_body.splitlines()
        if line.strip() and not line.strip().startswith("CHECK")
    }

    assert columns == schema_columns
    assert "uq_asset_source_links_source_external_active" in migration
    assert "uq_asset_source_links_asset_source_active" in migration
    assert "('admin', 'asset_links.view', true)" in migration
    assert "('operator', 'asset_links.view', true)" in migration
    assert "('management', 'asset_links.view', true)" in migration
    assert "('master', 'asset_links.view', false)" in migration


def test_asset_source_link_role_grants_match_requested_roles():
    from app.core import permissions

    assert "asset_links.view" in permissions.ROLE_DEFAULTS["admin"]
    assert "asset_links.view" in permissions.ROLE_DEFAULTS["operator"]
    assert "asset_links.view" in permissions.ROLE_DEFAULTS["management"]
    assert "asset_links.manage" in permissions.ROLE_DEFAULTS["admin"]
    assert "asset_links.manage" in permissions.ROLE_DEFAULTS["operator"]
    assert "asset_links.manage" not in permissions.ROLE_DEFAULTS["management"]
    assert "asset_links.view" not in permissions.ROLE_DEFAULTS["master"]
    assert "asset_links.view" in permissions.ROLE_DENIED["master"]
