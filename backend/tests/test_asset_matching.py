import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.integrations.base import SourceAdapter, SourceObject
from app.integrations.gtk_adapter import GtkSourceAdapter
from app.routers import asset_links as router
from app.services import asset_matching, gtk_matching

ROOT = Path(__file__).resolve().parents[2]
E2E_SCRIPT = ROOT / "backend" / "scripts" / "e2e_asset_unmatched.py"


def _asset(name: str, *, asset_type: str = "locomotive", inv: str = "I-1"):
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        inv_number=inv,
        asset_type=asset_type,
        series=None,
    )


def test_common_matcher_keeps_gtk_locomotive_report_result():
    gtk_row = SimpleNamespace(
        gtk_id=1,
        name="Locomotive",
        model_name="ПЭ-2М",
        garage_number="298",
        inventory_number="GTK-1",
    )
    assets = [_asset("ПЭ-2М 298")]
    gtk_result = gtk_matching.match_report("locomotive", [gtk_row], assets)
    generic_result = asset_matching.match_source_objects(
        [
            SourceObject(
                source="gtk",
                external_id="1",
                name=gtk_row.name,
                number=gtk_row.garage_number,
                inventory=gtk_row.inventory_number,
                model=gtk_row.model_name,
                type="locomotive",
            )
        ],
        assets,
    )
    assert gtk_result[0]["level"] == generic_result[0]["level"] == "high"
    assert gtk_result[0]["candidate_count"] == generic_result[0]["candidate_count"]
    assert gtk_result[0]["signals"] == generic_result[0]["signals"]


def test_generic_matcher_returns_ambiguous_and_none_levels():
    source = SourceObject(
        source="wialon",
        external_id="unit-1",
        name="ТЭМ18ДМ 3183",
        model="ТЭМ18 ДМ",
        type="diesel",
    )
    report = asset_matching.match_source_objects(
        [source],
        [_asset("ТЭМ18ДМ 3183", asset_type="diesel"),
         _asset("ТЭМ18ДМ 3183", asset_type="diesel", inv="I-2")],
    )
    assert report[0]["level"] == "ambiguous"
    assert report[0]["candidate_count"] == 2
    none = asset_matching.match_source_objects(
        [source], [_asset("ПЭ-2У 44")]
    )
    assert none[0]["level"] == "none"


def test_unmatched_e2e_script_has_valid_python_syntax():
    ast.parse(E2E_SCRIPT.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_gtk_adapter_implements_source_protocol_and_maps_mirror_rows():
    snapshot = {
        "locomotives": [
            {
                "gtk_id": 11,
                "name": "Loco",
                "garage_number": "298",
                "inventory_number": "L-11",
                "model_name": "ПЭ-2М",
            }
        ],
        "carriages": [
            {
                "gtk_id": 22,
                "name": "Wagon",
                "reg_number": "REG-22",
                "inventory_number": "W-22",
                "model_name": "Вагон",
            }
        ],
    }
    client = SimpleNamespace(fetch_snapshot=AsyncMock(return_value=snapshot))
    adapter = GtkSourceAdapter(client)
    assert isinstance(adapter, SourceAdapter)
    assert adapter.source == "gtk"
    assert adapter.mirror_table == "gtk_locomotives,gtk_carriages"
    result = await adapter.fetch_snapshot()
    assert result == [
        SourceObject(
            source="gtk",
            external_id="11",
            name="Loco",
            number="298",
            inventory="L-11",
            model="ПЭ-2М",
            type="locomotive",
        ),
        SourceObject(
            source="gtk",
            external_id="22",
            name="Wagon",
            number="REG-22",
            inventory="W-22",
            model="Вагон",
            type="carriage",
        ),
    ]


@pytest.mark.asyncio
async def test_unmatched_endpoint_is_paginated_and_uses_shared_service():
    result = {
        "source": "gtk",
        "external_id": "11",
        "name": "Wagon",
        "number": "REG-11",
        "serial": None,
        "inventory": None,
        "model": "Вагон",
        "type": "carriage",
        "level": "none",
        "candidate_count": 0,
        "suggestion": None,
        "candidates": [],
        "signals": [],
    }
    with patch.object(
        asset_matching,
        "list_unmatched",
        new=AsyncMock(return_value=([result], 3)),
    ):
        response = await router.list_unmatched_source_objects(
            SimpleNamespace(role="operator"),
            object(),
            "gtk",
            1,
            2,
        )
    assert response.total == 3
    assert response.limit == 1
    assert response.offset == 2
    assert response.items[0].external_id == "11"


@pytest.mark.asyncio
async def test_unmatched_service_uses_unlinked_gtk_mirror_and_shared_matching():
    from app.models.gtk import GtkCarriage

    carriage = GtkCarriage(
        gtk_id=11,
        name="Wagon",
        reg_number="REG-11",
        inventory_number=None,
        model_name="Вагон",
        is_active=True,
    )
    matching_asset = _asset("REG-11", asset_type="wagon", inv="REG-11")
    with (
        patch.object(
            asset_matching.gtk_repository,
            "list_unlinked_source_objects",
            new=AsyncMock(return_value=[carriage]),
        ),
        patch.object(
            asset_matching.assets_repository,
            "list_assets_unlinked_from_source",
            new=AsyncMock(return_value=[matching_asset]),
        ),
    ):
        items, total = await asset_matching.list_unmatched(
            object(), source="gtk", limit=10, offset=0
        )
    assert total == 1
    assert items[0]["external_id"] == "11"
    assert items[0]["level"] == "high"
    assert items[0]["suggestion"]["asset_id"] == matching_asset.id
