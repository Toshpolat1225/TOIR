from datetime import date, datetime, timezone
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.asset_field_policy import ASSET_FIELD_POLICY
from app.core.permissions import ROLE_DEFAULTS, ROLE_DENIED
from app.models.asset_field_changes import AssetFieldChange
from app.routers import asset_conflicts as router
from app.services import asset_field_changes as service
from app.services import gtk


EXPECTED_POLICY = {
    "inv_number": ("toir", "manual_only"),
    "org_unit_id": ("toir", "manual_only"),
    "asset_type": ("toir", "manual_only"),
    "accounting_inv_number": ("onec", "suggest_only"),
    "commissioned_at": ("onec", "suggest_only"),
    "serial_number": ("onec", "suggest_only"),
    "year_built": ("onec", "suggest_only"),
    "number": ("gtk", "auto_fill_if_empty"),
    "model_id": ("gtk", "auto_fill_if_empty"),
    "mileage": ("wialon", None),
    "online": ("wialon", None),
    "speed": ("wialon", None),
}
ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "backend" / "alembic" / "versions" / "0019_asset_field_changes.py"
E2E_SCRIPT = ROOT / "backend" / "scripts" / "e2e_asset_conflicts.py"
WIALON_IMPORT_SCRIPT = ROOT / "backend" / "scripts" / "wialon_import_assets.py"


def test_complete_asset_field_policy():
    assert {
        field: (policy.source, policy.mode)
        for field, policy in ASSET_FIELD_POLICY.items()
    } == EXPECTED_POLICY


def test_asset_conflict_permission_is_limited_to_admin_and_operator():
    assert "asset_conflicts.manage" in ROLE_DEFAULTS["admin"]
    assert "asset_conflicts.manage" in ROLE_DEFAULTS["operator"]
    assert "asset_conflicts.manage" not in ROLE_DEFAULTS["master"]
    assert "asset_conflicts.manage" not in ROLE_DEFAULTS["management"]
    assert "asset_conflicts.manage" in ROLE_DENIED["master"]
    assert "asset_conflicts.manage" in ROLE_DENIED["management"]


def test_asset_field_change_migration_follows_passport_and_seeds_permission():
    migration = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0019_asset_field_changes"' in migration
    assert len("0019_asset_field_changes") <= 32
    assert 'down_revision = "0018_asset_passport"' in migration
    assert "asset_field_changes" in migration
    assert "asset_conflicts.manage" in migration
    schema = (ROOT / "postgres" / "schema.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE asset_field_changes" in schema
    paths = {route.path for route in router.router.routes}
    assert "/asset-conflicts" in paths
    assert "/asset-conflicts/{change_id}/accept" in paths
    assert "/asset-conflicts/{change_id}/reject" in paths
    ast.parse(E2E_SCRIPT.read_text(encoding="utf-8"))
    ast.parse(WIALON_IMPORT_SCRIPT.read_text(encoding="utf-8"))
    assert "record_manual_changes" in WIALON_IMPORT_SCRIPT.read_text(encoding="utf-8")


def test_manual_org_unit_move_is_recorded_in_change_journal():
    db = SimpleNamespace(add=Mock())
    asset = SimpleNamespace(id=uuid4())
    old_section, new_section = uuid4(), uuid4()
    service.record_manual_changes(
        db,
        asset,
        old_values={"org_unit_id": old_section},
        new_values={"org_unit_id": new_section},
    )
    change = db.add.call_args.args[0]
    assert change.field == "org_unit_id"
    assert change.old_value == str(old_section)
    assert change.new_value == str(new_section)
    assert (change.source, change.kind, change.status) == ("toir", "manual", "applied")


def test_manual_normalization_only_change_is_still_audited():
    db = SimpleNamespace(add=Mock())
    asset = SimpleNamespace(id=uuid4())
    service.record_manual_changes(
        db,
        asset,
        old_values={"number": "ПЭ-2М"},
        new_values={"number": "ПЭ2М"},
    )
    assert db.add.call_count == 1
    assert db.add.call_args.args[0].field == "number"


@pytest.mark.asyncio
async def test_conflict_list_returns_paginated_shape():
    row = AssetFieldChange(
        id=1,
        asset_id=uuid4(),
        field="year_built",
        old_value=None,
        new_value=2000,
        source="onec",
        kind="conflict",
        status="pending",
        created_at=datetime.now(timezone.utc),
        resolved_by=None,
        resolved_at=None,
    )
    with patch.object(
        service,
        "list_conflicts",
        new=AsyncMock(return_value=([row], 1)),
    ):
        response = await router.list_asset_conflicts(
            SimpleNamespace(role="operator"),
            object(),
            "pending",
            25,
            10,
        )
    assert response.total == 1
    assert response.limit == 25
    assert response.offset == 10
    assert response.items[0].field == "year_built"


@pytest.mark.asyncio
async def test_auto_fill_only_writes_empty_value_and_journals_applied():
    asset = SimpleNamespace(
        id=uuid4(), number=None, number_normalized=None, asset_type="wagon"
    )
    db = SimpleNamespace()
    with (
        patch.object(
            service.repository,
            "get_asset_for_update",
            new=AsyncMock(return_value=asset),
        ),
        patch.object(service.repository, "add", new=AsyncMock()) as add_change,
    ):
        result = await service.propose_field(
            db, asset_id=asset.id, field="number", value="00123", source="gtk"
        )
    assert result == "applied"
    assert asset.number == "00123"
    assert asset.number_normalized == "00123"
    change = add_change.await_args.args[1]
    assert (change.kind, change.status, change.old_value, change.new_value) == (
        "auto_fill",
        "applied",
        None,
        "00123",
    )


@pytest.mark.asyncio
async def test_different_nonempty_value_creates_conflict_without_mutation():
    asset = SimpleNamespace(id=uuid4(), number="123", asset_type="wagon")
    db = SimpleNamespace()
    with (
        patch.object(
            service.repository,
            "list_pending_for_field",
            new=AsyncMock(return_value=[]),
        ),
        patch.object(
            service.repository,
            "get_asset_for_update",
            new=AsyncMock(return_value=asset),
        ),
        patch.object(service.repository, "add", new=AsyncMock()) as add_change,
    ):
        result = await service.propose_field(
            db, asset_id=asset.id, field="number", value="456", source="gtk"
        )
    assert result == "pending"
    assert asset.number == "123"
    change = add_change.await_args.args[1]
    assert (change.kind, change.status, change.old_value, change.new_value) == (
        "conflict",
        "pending",
        "123",
        "456",
    )


@pytest.mark.asyncio
async def test_empty_suggest_only_field_creates_pending_proposal():
    asset = SimpleNamespace(id=uuid4(), year_built=None)
    with (
        patch.object(
            service.repository,
            "get_asset_for_update",
            new=AsyncMock(return_value=asset),
        ),
        patch.object(
            service.repository,
            "list_pending_for_field",
            new=AsyncMock(return_value=[]),
        ),
        patch.object(service.repository, "add", new=AsyncMock()) as add_change,
    ):
        result = await service.propose_field(
            object(), asset_id=asset.id, field="year_built", value=1998, source="onec"
        )
    assert result == "pending"
    assert asset.year_built is None
    change = add_change.await_args.args[1]
    assert (change.kind, change.status, change.new_value) == (
        "conflict",
        "pending",
        1998,
    )


@pytest.mark.asyncio
async def test_normalized_equal_values_do_not_create_change():
    asset = SimpleNamespace(id=uuid4(), number="ПЭ-2М 111", asset_type="wagon")
    with (
        patch.object(
            service.repository,
            "get_asset_for_update",
            new=AsyncMock(return_value=asset),
        ),
        patch.object(service.repository, "add", new=AsyncMock()) as add_change,
    ):
        result = await service.propose_field(
            object(), asset_id=asset.id, field="number", value="ПЭ2М 111", source="gtk"
        )
    assert result == "unchanged"
    add_change.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_normalized_pending_proposal_is_not_added():
    existing = SimpleNamespace(new_value="ПЭ-2М 111")
    asset = SimpleNamespace(id=uuid4(), number="different", asset_type="wagon")
    with (
        patch.object(
            service.repository,
            "list_pending_for_field",
            new=AsyncMock(return_value=[existing]),
        ),
        patch.object(
            service.repository,
            "get_asset_for_update",
            new=AsyncMock(return_value=asset),
        ),
        patch.object(service.repository, "add", new=AsyncMock()) as add_change,
    ):
        result = await service.propose_field(
            object(), asset_id=asset.id, field="number", value="ПЭ2М 111", source="gtk"
        )
    assert result == "duplicate"
    assert asset.number == "different"
    add_change.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_only_proposal_is_rejected_and_logged(caplog):
    asset = SimpleNamespace(id=uuid4(), inv_number="ORG-1")
    result = await service.propose_field(
        object(), asset_id=asset.id, field="inv_number", value="ORG-2", source="gtk"
    )
    assert result == "rejected"
    assert asset.inv_number == "ORG-1"
    assert "non-owning source" in caplog.text


@pytest.mark.asyncio
async def test_accept_applies_pending_value_and_marks_resolved():
    change = AssetFieldChange(
        id=1,
        asset_id=uuid4(),
        field="commissioned_at",
        old_value=None,
        new_value="2020-01-02",
        source="onec",
        kind="conflict",
        status="pending",
    )
    asset = SimpleNamespace(
        commissioned_at=None,
        updated_at=None,
    )
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
    with (
        patch.object(
            service.repository,
            "get_change_for_update",
            new=AsyncMock(return_value=change),
        ),
        patch.object(
            service.repository,
            "get_asset_for_update",
            new=AsyncMock(return_value=asset),
        ),
    ):
        result = await service.accept_conflict(db, 1, uuid4())
    assert result.status == "accepted"
    assert asset.commissioned_at == date(2020, 1, 2)
    assert result.resolved_by is not None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_reject_marks_pending_change_resolved_without_asset_write():
    change = AssetFieldChange(
        id=2,
        asset_id=uuid4(),
        field="year_built",
        old_value=2000,
        new_value=2001,
        source="onec",
        kind="conflict",
        status="pending",
    )
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
    with patch.object(
        service.repository,
        "get_change_for_update",
        new=AsyncMock(return_value=change),
    ):
        result = await service.reject_conflict(db, 2, uuid4())
    assert result.status == "rejected"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_accept_returns_409_when_field_changed_since_proposal():
    change = AssetFieldChange(
        id=3,
        asset_id=uuid4(),
        field="year_built",
        old_value=2000,
        new_value=2001,
        source="onec",
        kind="conflict",
        status="pending",
    )
    asset = SimpleNamespace(year_built=2002)
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())
    with (
        patch.object(
            service.repository,
            "get_change_for_update",
            new=AsyncMock(return_value=change),
        ),
        patch.object(
            service.repository,
            "get_asset_for_update",
            new=AsyncMock(return_value=asset),
        ),
        pytest.raises(HTTPException) as error,
    ):
        await service.accept_conflict(db, 3, uuid4())
    assert error.value.status_code == 409
    db.commit.assert_not_awaited()


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_):
        return False


@pytest.mark.asyncio
async def test_gtk_proposal_failure_does_not_escape_sync_helper(caplog):
    session = SimpleNamespace(begin=lambda: _AsyncContext(None))
    with (
        patch.object(gtk, "SessionFactory", return_value=_AsyncContext(session)),
        patch.object(
            gtk,
            "_propose_gtk_passport_fields",
            new=AsyncMock(side_effect=RuntimeError("test database failure")),
        ),
    ):
        await gtk._run_gtk_passport_proposals({"carriages": []})
    assert "GTK passport field proposals failed" in caplog.text


@pytest.mark.asyncio
async def test_gtk_sync_proposes_only_for_active_linked_carriages():
    asset = SimpleNamespace(id=uuid4(), model_id=None, asset_type="wagon")
    snapshot = {
        "carriages": [
            {"gtk_id": 11, "reg_number": "R-11", "model_name": None},
            {"gtk_id": 12, "reg_number": "R-12", "model_name": None},
        ]
    }
    db = object()
    with (
        patch.object(
            gtk.repository,
            "get_linked_assets_for_update",
            new=AsyncMock(return_value={"11": asset}),
        ),
        patch.object(
            gtk.field_changes_service,
            "propose_field",
            new=AsyncMock(return_value="pending"),
        ) as propose,
    ):
        await gtk._propose_gtk_passport_fields(db, snapshot)
    propose.assert_awaited_once_with(
        db,
        asset_id=asset.id,
        field="number",
        value="R-11",
        source="gtk",
    )
