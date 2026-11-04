from __future__ import annotations

import ast
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.core.permissions import ROLE_DEFAULTS, ROLE_DENIED, require_permission
from app.models.asset_field_changes import AssetFieldChange
from app.models.asset_models import AssetModel
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.routers import assets as assets_router
from app.services import asset_links, assets as assets_service

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "backend" / "alembic" / "versions"
SCHEMA = ROOT / "postgres" / "schema.sql"
FRONTEND_FILES = (
    ROOT / "app" / "dashboard" / "os" / "page.tsx",
    ROOT / "app" / "dashboard" / "os" / "conflicts" / "page.tsx",
    ROOT / "app" / "dashboard" / "os" / "gtk" / "page.tsx",
    ROOT / "lib" / "api.ts",
)


def _revision(path: Path) -> tuple[str, str | None]:
    module = ast.parse(path.read_text(encoding="utf-8"))
    values = {}
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                    values[target.id] = ast.literal_eval(node.value)
    return values["revision"], values["down_revision"]


def _schema_columns(table: str) -> set[str]:
    schema = SCHEMA.read_text(encoding="utf-8")
    body = schema.split(f"CREATE TABLE {table} (", 1)[1].split("\n);", 1)[0]
    return {
        line.strip().split()[0]
        for line in body.splitlines()
        if line.strip()
        and not line.strip().startswith(("CONSTRAINT", "--"))
    }


def test_p6_migration_chain_is_linear_from_0012_to_head():
    paths = sorted(MIGRATIONS.glob("001[2-9]_*.py"))
    revisions = [_revision(path) for path in paths]
    assert len(revisions) == 8
    assert len({revision for revision, _ in revisions}) == len(revisions)
    assert all(len(revision) <= 32 for revision, _ in revisions)
    assert [down for _, down in revisions] == [
        "0011_wialon_counter_state",
        "0012_wialon_units",
        "0013_gtk_source",
        "0014_fixed_assets_gtk_id",
        "0015_gtk_wagon_mileage",
        "0016_gtk_mirror_cleanup",
        "0017_asset_source_links",
        "0018_asset_passport",
    ]
    assert revisions[-1][0] == "0019_asset_field_changes"


def test_p6_0017_to_0019_migration_operations_have_matching_downgrades():
    source_links = (MIGRATIONS / "0017_asset_source_links.py").read_text(encoding="utf-8")
    passport = (MIGRATIONS / "0018_asset_passport.py").read_text(encoding="utf-8")
    field_changes = (MIGRATIONS / "0019_asset_field_changes.py").read_text(encoding="utf-8")
    assert "op.create_table(" in source_links and "op.drop_table(" in source_links
    assert "op.create_index(" in source_links and "op.drop_index(" in source_links
    assert "def downgrade()" in passport and "op.drop_table(\"asset_models\")" in passport
    assert "op.drop_column(\"fixed_assets\", column)" in passport
    assert "def downgrade()" in field_changes
    assert "op.drop_table(\"asset_field_changes\")" in field_changes


def test_p6_asset_models_and_links_match_orm_and_canonical_schema():
    for model in (AssetSourceLink, AssetModel, AssetFieldChange, FixedAsset):
        assert set(model.__table__.columns.keys()) == _schema_columns(model.__tablename__)

    schema = SCHEMA.read_text(encoding="utf-8")
    assert "uq_asset_source_links_source_external_active" in schema
    assert "uq_asset_source_links_asset_source_active" in schema
    assert "uq_fixed_assets_inv_number_real" in schema
    assert "uq_fixed_assets_accounting_inv_number" in schema
    assert "ck_fixed_assets_year_built_min" in schema
    assert "ck_fixed_assets_commissioned_at_year_built" in schema
    assert "ck_fixed_assets_decommissioned_at_commissioned_at" in schema


def test_p6_offline_migration_render_is_blocked_by_data_dependent_passport_backfill():
    env = (ROOT / "backend" / "alembic" / "env.py").read_text(encoding="utf-8")
    passport = (MIGRATIONS / "0018_asset_passport.py").read_text(encoding="utf-8")
    assert "def run_migrations_offline()" in env
    assert "if context.is_offline_mode()" in env
    assert "op.get_bind()" in passport
    assert "bind.execute(" in passport


def test_p6_permission_seeds_and_runtime_denials_are_consistent():
    links_migration = (MIGRATIONS / "0017_asset_source_links.py").read_text(encoding="utf-8")
    conflicts_migration = (MIGRATIONS / "0019_asset_field_changes.py").read_text(encoding="utf-8")
    assert "('admin', 'asset_links.view', true)" in links_migration
    assert "('operator', 'asset_links.view', true)" in links_migration
    assert "('management', 'asset_links.view', true)" in links_migration
    assert "('master', 'asset_links.view', false)" in links_migration
    assert "('management', 'asset_links.manage', false)" in links_migration
    assert "('master', 'asset_links.manage', false)" in links_migration
    assert "('admin', 'asset_conflicts.manage', true)" in conflicts_migration
    assert "('operator', 'asset_conflicts.manage', true)" in conflicts_migration
    assert "('master', 'asset_conflicts.manage', false)" in conflicts_migration
    assert "asset_links.view" in ROLE_DEFAULTS["management"]
    assert "asset_links.manage" not in ROLE_DEFAULTS["management"]
    assert "asset_links.manage" not in ROLE_DEFAULTS["master"]
    assert "asset_conflicts.manage" not in ROLE_DEFAULTS["master"]
    assert {"asset_links.view", "asset_links.manage", "asset_conflicts.manage"} <= ROLE_DENIED["master"]


@pytest.mark.asyncio
async def test_p6_permission_dependency_returns_403_for_ungranted_roles():
    class Result:
        def scalar_one_or_none(self):
            return None

    db = SimpleNamespace(execute=AsyncMock(return_value=Result()))
    master = SimpleNamespace(role="master")
    management = SimpleNamespace(role="management")
    with pytest.raises(HTTPException) as master_error:
        await require_permission("asset_links.view")(master, db)
    with pytest.raises(HTTPException) as management_error:
        await require_permission("asset_links.manage")(management, db)
    assert master_error.value.status_code == 403
    assert management_error.value.status_code == 403


@pytest.mark.asyncio
async def test_p6_model_list_endpoint_returns_schema_pagination():
    model = AssetModel(
        id=uuid4(),
        name="Wagon model",
        name_normalized="wagonmodel",
        asset_type="wagon",
        series="Wagon model",
    )
    with patch(
        "app.services.asset_passport.list_models",
        new=AsyncMock(return_value=([model], 1)),
    ):
        response = await assets_router.get_asset_models(
            SimpleNamespace(), object(), "wagon", None, 25, 10
        )
    assert response.model_dump() == {
        "items": [
            {
                "id": model.id,
                "name": "Wagon model",
                "name_normalized": "wagonmodel",
                "asset_type": "wagon",
                "series": "Wagon model",
            }
        ],
        "total": 1,
        "limit": 25,
        "offset": 10,
    }


@pytest.mark.asyncio
async def test_p6_generic_link_endpoint_maps_commit_integrity_race_to_409():
    db = SimpleNamespace(
        commit=AsyncMock(side_effect=IntegrityError("commit", {}, RuntimeError("unique"))),
        rollback=AsyncMock(),
        refresh=AsyncMock(),
    )
    link = SimpleNamespace()
    with (
        patch.object(assets_service, "get_fixed_asset", new=AsyncMock()),
        patch.object(asset_links, "link", new=AsyncMock(return_value=link)),
    ):
        with pytest.raises(HTTPException) as error:
            await assets_router.post_fixed_asset_link(
                uuid4(),
                assets_router.AssetSourceLinkCreate(
                    source="wialon", external_id="unit-1"
                ),
                SimpleNamespace(id=uuid4()),
                db,
            )
    assert error.value.status_code == 409
    db.rollback.assert_awaited_once()
    db.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_p6_asset_patch_replaces_provisional_wialon_number_with_real_number():
    asset = SimpleNamespace(
        id=uuid4(),
        gtk_id=None,
        wialon_id=None,
        asset_type="diesel",
        model_id=None,
        number=None,
        number_normalized=None,
        inv_number="WIALON-unit-1",
        inv_number_is_provisional=True,
        updated_at=None,
        section_id=None,
        mileage=None,
    )
    with (
        patch.object(assets_service, "_get_scoped_asset", new=AsyncMock(return_value=asset)),
        patch.object(assets_service.asset_links_repository, "get_active", new=AsyncMock(return_value=[])),
        patch.object(assets_service, "_commit", new=AsyncMock()),
        patch.object(assets_service, "asset_read", return_value=asset),
    ):
        db = SimpleNamespace(refresh=AsyncMock(), add=lambda _: None)
        await assets_service.update_fixed_asset(
            db, asset.id, assets_service.FixedAssetUpdate(inv_number="REAL-123")
        )
    assert asset.inv_number == "REAL-123"
    assert asset.inv_number_is_provisional is False


def test_p6_ui_uses_russian_text_and_has_no_forbidden_alphabet_or_non_english_comments():
    forbidden_alphabet = re.compile(r"[өүӨҮқғҳў]")
    cyrillic = re.compile(r"[А-Яа-яЁё]")
    for path in FRONTEND_FILES:
        text = path.read_text(encoding="utf-8")
        assert forbidden_alphabet.search(text) is None, path.name
        in_block_comment = False
        for line in text.splitlines():
            stripped = line.strip()
            if "/*" in line:
                in_block_comment = True
            is_comment = (
                in_block_comment
                or stripped.startswith("//")
                or stripped.startswith("*")
            )
            if is_comment:
                assert cyrillic.search(line) is None, f"{path.name}: {line}"
            if "*/" in line:
                in_block_comment = False


def test_p6_passport_report_is_exact_match_only_and_decision_documents_mapping_followup():
    report_source = (ROOT / "backend" / "app" / "services" / "asset_passport.py").read_text(encoding="utf-8")
    decision = (ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
    assert "sections_by_name.get(asset.depot, [])" in report_source
    assert "asset.depot = section.name" in (MIGRATIONS / "0018_asset_passport.py").read_text(encoding="utf-8")
    assert "86/86" in decision
    assert "mapping" in decision.lower()


def test_p6_legacy_source_mirror_references_have_removal_inventory():
    references = {
        "backend/app/models/assets.py",
        "backend/app/schemas/assets.py",
        "backend/app/services/assets.py",
        "backend/app/services/asset_links.py",
        "backend/app/services/wialon_units.py",
        "backend/app/repositories/wialon_counters.py",
        "backend/app/repositories/assets.py",
        "backend/app/services/wialon_bootstrap_plan.py",
        "backend/app/routers/assets.py",
    }
    all_source = "\n".join(
        path.read_text(encoding="utf-8")
        for folder in (ROOT / "backend" / "app", ROOT / "app", ROOT / "lib")
        for path in folder.rglob("*")
        if path.suffix in {".py", ".ts", ".tsx"}
    )
    assert "wialon_id" in all_source and "gtk_id" in all_source
    assert all((ROOT / path).exists() for path in references)
    assert "drop_column(\"fixed_assets\", \"gtk_id\")" not in (
        MIGRATIONS / "0019_asset_field_changes.py"
    ).read_text(encoding="utf-8")
