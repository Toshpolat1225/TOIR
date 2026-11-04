from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.schemas.assets import FixedAssetCreate, FixedAssetUpdate
from app.routers import assets as assets_router
from app.services import asset_passport
from app.services import assets as assets_service
from app.services.gtk_matching import extract_series, normalize_token


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "backend" / "alembic" / "versions" / "0018_asset_passport.py"


def test_number_extraction_ignores_parenthesized_second_number():
    name = "ПЭ-2М 111 (353)"
    assert asset_passport.extract_passport_number(
        name, series=extract_series(name)
    ) == "111"
    assert normalize_token("ПЭ-2М 111") == normalize_token("ПЭ2М 111")


def test_backfill_merges_normalized_model_duplicates_and_is_repeatable():
    rows = [
        {
            "id": uuid4(),
            "name": "ТЭМ18ДМ 1234",
            "series": "ТЭМ18ДМ",
            "asset_type": "diesel",
            "inv_number": "WIALON-unit-1",
            "comm_date": date(2000, 1, 2),
        },
        {
            "id": uuid4(),
            "name": "тэм18дм 1234",
            "series": "тэм18дм",
            "asset_type": "diesel",
            "inv_number": "ORG-2",
            "comm_date": None,
        },
    ]
    planned = asset_passport.plan_passport_backfill(rows)
    assert planned == asset_passport.plan_passport_backfill(rows)
    models, assets = planned
    assert len(models) == 1
    assert models[0]["name_normalized"] == normalize_token("ТЭМ18ДМ")
    assert [row["number"] for row in assets] == ["1234", "1234"]
    assert assets[0]["number_normalized"] == "1234"
    assert assets[0]["commissioned_at"] == date(2000, 1, 2)
    assert assets[0]["inv_number_is_provisional"] is True
    assert assets[1]["inv_number_is_provisional"] is False

    migration = MIGRATION.read_text(encoding="utf-8")
    assert "on_conflict_do_nothing" in migration
    assert "0017_asset_source_links" in migration
    assert "revision = \"0018_asset_passport\"" in migration
    assert "HAVING count(*) = 1" in migration
    assert "asset.depot = section.name" in migration
    assert "uq_fixed_assets_active_model_number" in migration
    assert "ix_fixed_assets_type_model_number" in migration


def test_passport_check_rules_reject_invalid_year_and_dates():
    with pytest.raises(ValueError):
        asset_passport.validate_passport_values(
            year_built=1899,
            commissioned_at=None,
            decommissioned_at=None,
            current_year=2026,
        )
    with pytest.raises(ValueError):
        asset_passport.validate_passport_values(
            year_built=2020,
            commissioned_at=date(2019, 12, 31),
            decommissioned_at=None,
            current_year=2026,
        )
    with pytest.raises(ValueError):
        asset_passport.validate_passport_values(
            year_built=None,
            commissioned_at=date(2020, 1, 1),
            decommissioned_at=date(2019, 12, 31),
            current_year=2026,
        )
    assert "postgresql_not_valid=True" in MIGRATION.read_text(encoding="utf-8")


def test_provisional_inventory_numbers_may_repeat_but_real_numbers_may_not():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE assets (inv_number TEXT, inv_number_is_provisional BOOLEAN)"
    )
    connection.execute(
        "CREATE UNIQUE INDEX uq_inv_real ON assets(inv_number) "
        "WHERE inv_number_is_provisional IS FALSE"
    )
    connection.execute("INSERT INTO assets VALUES ('WIALON-1', TRUE)")
    connection.execute("INSERT INTO assets VALUES ('WIALON-1', TRUE)")
    connection.execute("INSERT INTO assets VALUES ('ORG-1', FALSE)")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO assets VALUES ('ORG-1', FALSE)")
    migration = MIGRATION.read_text(encoding="utf-8")
    assert "uq_fixed_assets_inv_number_real" in migration
    assert "inv_number_is_provisional IS FALSE" in migration


def test_duplicate_number_groups_are_reported():
    model_id = uuid4()
    assets = [
        SimpleNamespace(
            id=uuid4(),
            inv_number=f"ORG-{index}",
            asset_type="diesel",
            model_id=model_id,
            number_normalized="1234",
            depot="Section A" if index == 1 else "Legacy depot",
            org_unit_id=None,
            year_built=1899 if index == 1 else None,
            commissioned_at=date(1898, 1, 1) if index == 1 else None,
            decommissioned_at=date(1897, 1, 1) if index == 1 else None,
        )
        for index in (1, 2)
    ]
    report = asset_passport.build_passport_report(
        assets, [(uuid4(), "Section A")], current_year=2026
    )
    assert len(report["depot_matches"]) == 1
    assert report["depot_unmatched"][0]["status"] == "no_match"
    assert len(report["duplicate_numbers"]) == 1
    assert len(report["duplicate_numbers"][0]["assets"]) == 2
    assert len(report["invalid_values"]) == 1


@pytest.mark.asyncio
async def test_missing_name_is_generated_from_model_and_number():
    model = SimpleNamespace(
        id=uuid4(),
        name="ТЭМ18ДМ",
        series="ТЭМ18ДМ",
        asset_type="diesel",
    )
    with patch.object(
        asset_passport.repository,
        "add_if_missing",
        new=AsyncMock(return_value=model),
    ):
        prepared = await asset_passport.prepare_new_asset(
            object(),
            asset_type="diesel",
            name=None,
            model_id=None,
            model_name="ТЭМ18ДМ",
            number="1234",
        )
    assert prepared["name"] == "ТЭМ18ДМ 1234"
    assert prepared["number_normalized"] == "1234"
    assert prepared["model_id"] == model.id


def test_new_create_schema_keeps_name_and_passport_fields_optional():
    payload = FixedAssetCreate(inv_number="ORG-1", asset_type="diesel")
    assert payload.name is None
    assert payload.number is None
    assert payload.model_id is None


@pytest.mark.asyncio
async def test_patch_recomputes_normalized_number():
    asset = SimpleNamespace(
        id=uuid4(),
        gtk_id=None,
        wialon_id=None,
        asset_type="diesel",
        model_id=None,
        number=None,
        number_normalized=None,
        inv_number="ORG-1",
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
            assets_service.asset_links_repository,
            "get_active",
            new=AsyncMock(return_value=[]),
        ),
        patch.object(assets_service, "_commit", new=AsyncMock()),
        patch.object(assets_service, "asset_read", return_value=asset),
    ):
        await assets_service.update_fixed_asset(
            SimpleNamespace(refresh=AsyncMock()),
            asset.id,
            FixedAssetUpdate(number="ПЭ-2М 111"),
        )
    assert asset.number == "ПЭ-2М 111"
    assert asset.number_normalized == normalize_token("ПЭ-2М 111")


@pytest.mark.asyncio
async def test_passport_report_endpoint_supports_json_and_csv_for_admin_operator():
    report = {
        "depot_matches": [],
        "depot_unmatched": [],
        "duplicate_numbers": [],
        "invalid_values": [],
    }
    with patch.object(
        assets_service,
        "get_fixed_asset_passport_report",
        new=AsyncMock(return_value=report),
    ):
        result = await assets_router.get_fixed_asset_passport_report(
            SimpleNamespace(role="operator"), object(), "json"
        )
        response = await assets_router.get_fixed_asset_passport_report(
            SimpleNamespace(role="admin"),
            object(),
            "csv",
        )
    assert result == report
    assert response.media_type.startswith("text/csv")
    assert b"category,asset_id,inv_number" in response.body
    with pytest.raises(HTTPException) as forbidden:
        await assets_router.get_fixed_asset_passport_report(
            SimpleNamespace(role="management"), object(), "json"
        )
    assert getattr(forbidden.value, "status_code", None) == 403
