import unittest
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.integrations.wialon_client import WialonUnit
from app.models.wialon_units import WialonUnitRecord
from app.routers import assets as assets_router
from app.routers import wialon as wialon_router
from app.repositories import wialon_units as repository
from app.schemas.assets import FixedAssetRead, FixedAssetUpdate
from app.schemas.wialon import WialonCreateAssetRequest
from app.services import assets, wialon_units


def _fixed_asset_read() -> FixedAssetRead:
    now = datetime.now(timezone.utc)
    return FixedAssetRead(
        id=uuid4(),
        inv_number="W-1",
        name="Wialon unit",
        asset_type="diesel",
        series=None,
        depot=None,
        section_id=None,
        number=None,
        number_normalized=None,
        serial_number=None,
        model_id=None,
        accounting_inv_number=None,
        org_unit_id=None,
        commissioned_at=None,
        decommissioned_at=None,
        inv_number_is_provisional=False,
        status="operational",
        comm_date=None,
        year_built=None,
        mileage=Decimal("0"),
        last_maint_date=None,
        next_maint_date=None,
        initial_cost=None,
        owner=None,
        wialon_id="unit-1",
        wialon_last_sync=now,
        wialon_speed=None,
        wialon_online=False,
        failure_probability=None,
        health_score=None,
        predicted_failure_km=None,
        last_ml_update=None,
        created_at=now,
        updated_at=now,
    )


class WialonUnitRepositoryTests(unittest.IsolatedAsyncioTestCase):
    def test_unit_model_has_requested_fields_without_foreign_keys(self):
        table = WialonUnitRecord.__table__
        self.assertEqual(table.c.unit_id.type.length, 100)
        self.assertEqual(table.c.cnm.type.precision, 16)
        self.assertEqual(table.c.cnm.type.scale, 2)
        self.assertEqual(table.c.cneh.type.precision, 14)
        self.assertEqual(table.c.cneh.type.scale, 3)
        self.assertEqual(table.c.speed.type.precision, 6)
        self.assertEqual(table.c.speed.type.scale, 2)
        self.assertEqual(
            set(table.columns.keys()),
            {
                "unit_id",
                "name",
                "cnm",
                "cneh",
                "calc_flags",
                "speed",
                "last_message_at",
                "suspect_absolute",
                "first_seen_at",
                "last_synced_at",
                "updated_at",
            },
        )
        self.assertFalse(any(column.foreign_keys for column in table.columns))

    async def test_unit_upsert_is_idempotent_and_does_not_commit(self):
        unit = WialonUnit(
            "unit-1",
            "ТЭМ18 ДМ 3183",
            None,
            Decimal("0"),
            Decimal("1007343489"),
            Decimal("0"),
            7,
        )
        now = datetime.now(timezone.utc)
        statement = repository.build_upsert_statement([unit], synced_at=now)
        sql = str(statement.compile(dialect=postgresql.dialect()))
        self.assertIn("ON CONFLICT (unit_id) DO UPDATE", sql)
        self.assertIn("suspect_absolute", sql)
        self.assertNotIn("first_seen_at", sql)

        db = SimpleNamespace(execute=AsyncMock(), flush=AsyncMock())
        await repository.upsert_units(db, [unit], synced_at=now)

        db.execute.assert_awaited_once()
        db.flush.assert_awaited_once()
        self.assertFalse(hasattr(db, "commit"))


class WialonUnitServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_requested_read_and_write_routes_are_registered(self):
        fixed_asset_paths = {route.path for route in assets_router.router.routes}
        wialon_paths = {route.path for route in wialon_router.router.routes}
        self.assertIn("/fixed-assets/unified", fixed_asset_paths)
        self.assertIn("/wialon/units", wialon_paths)
        self.assertIn("/wialon/units/{unit_id}", wialon_paths)
        self.assertIn("/wialon/units/{unit_id}/suggestions", wialon_paths)
        self.assertIn("/wialon/units/{unit_id}/create-asset", wialon_paths)

    async def test_only_admin_and_operator_can_create_from_wialon(self):
        with self.assertRaises(HTTPException) as raised:
            await wialon_router.post_wialon_unit_create_asset(
                "unit-1",
                WialonCreateAssetRequest(
                    inv_number="W-1",
                    asset_type="diesel",
                ),
                SimpleNamespace(role="management"),
                object(),
                object(),
            )
        self.assertEqual(raised.exception.status_code, 403)

    async def test_create_asset_uses_zero_mileage_for_suspect_unit(self):
        now = datetime.now(timezone.utc)
        unit = SimpleNamespace(
            unit_id="unit-1",
            name="HILUX 366",
            cnm=Decimal("1007343489"),
            cneh=Decimal("0"),
            speed=Decimal("0"),
            last_message_at=now,
            last_synced_at=now,
            suspect_absolute=True,
        )
        db = SimpleNamespace(
            flush=AsyncMock(),
            commit=AsyncMock(),
            rollback=AsyncMock(),
            refresh=AsyncMock(),
        )
        with (
            patch.object(
                wialon_units.repository,
                "get_unit_record",
                new=AsyncMock(return_value=unit),
            ),
            patch.object(
                wialon_units.repository,
                "get_linked_asset",
                new=AsyncMock(return_value=None),
            ),
            patch.object(
                wialon_units.assets_repository,
                "active_catalog_value_exists",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                wialon_units.assets_repository,
                "add_asset",
                new=AsyncMock(),
            ) as add_asset,
            patch.object(
                wialon_units.asset_passport,
                "prepare_new_asset",
                new=AsyncMock(
                    return_value={
                        "name": "HILUX 366",
                        "model_id": uuid4(),
                        "series": "HILUX",
                        "number": "366",
                        "number_normalized": "366",
                    }
                ),
            ),
            patch.object(
                wialon_units.asset_links_service,
                "link",
                new=AsyncMock(),
            ) as save_link,
            patch.object(
                wialon_units.counters_repository,
                "save_decision",
                new=AsyncMock(),
            ) as save_decision,
            patch.object(
                wialon_units.assets_repository,
                "add_mileage_history",
                new=AsyncMock(),
            ) as add_history,
            patch.object(wialon_units, "asset_read", return_value=_fixed_asset_read()),
        ):
            result = await wialon_units.create_asset_from_wialon_unit(
                db,
                "unit-1",
                WialonCreateAssetRequest(
                    inv_number="W-1",
                    asset_type="diesel",
                ),
            )

        created_asset = add_asset.await_args.args[1]
        self.assertEqual(created_asset.mileage, Decimal("0"))
        self.assertEqual(created_asset.wialon_id, "unit-1")
        save_link.assert_awaited_once()
        self.assertIn("manual correction", result.warning)
        save_decision.assert_awaited_once()
        self.assertEqual(save_decision.await_args.args[3].mileage.verdict.value, "baseline")
        add_history.assert_awaited_once_with(db, created_asset.id, Decimal("0"), "wialon")
        db.commit.assert_awaited_once()

    async def test_invalid_asset_type_is_rejected_by_request_schema(self):
        with self.assertRaises(ValidationError):
            WialonCreateAssetRequest(
                inv_number="W-1",
                asset_type="other",
            )

    async def test_create_asset_rejects_duplicate_wialon_id(self):
        unit = SimpleNamespace(unit_id="unit-1")
        db = SimpleNamespace(commit=AsyncMock())
        with (
            patch.object(
                wialon_units.repository,
                "get_unit_record",
                new=AsyncMock(return_value=unit),
            ),
            patch.object(
                wialon_units.repository,
                "get_linked_asset",
                new=AsyncMock(return_value=SimpleNamespace(id=uuid4())),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await wialon_units.create_asset_from_wialon_unit(
                    db,
                    "unit-1",
                    WialonCreateAssetRequest(
                        inv_number="W-1",
                        asset_type="diesel",
                    ),
                )
        self.assertEqual(raised.exception.status_code, 409)
        db.commit.assert_not_awaited()

    async def test_suggestions_require_matching_series_and_unit_number(self):
        unit = SimpleNamespace(
            unit_id="unit-1",
            name="ТЭМ18 ДМ 3183",
        )
        candidate = SimpleNamespace(
            id=uuid4(),
            name="ТЭМ18 ДМ 3183",
            inv_number="A-1",
            asset_type="diesel",
            series="TEM18 DM",
            section_id=uuid4(),
        )
        other_series = SimpleNamespace(
            id=uuid4(),
            name="ПЭ-2у 3183",
            inv_number="A-2",
            asset_type="locomotive",
            series="ПЭ-2у",
            section_id=None,
        )
        with (
            patch.object(
                wialon_units.repository,
                "get_unit_record",
                new=AsyncMock(return_value=unit),
            ),
            patch.object(
                wialon_units.repository,
                "get_linked_asset",
                new=AsyncMock(return_value=None),
            ),
            patch.object(
                wialon_units.repository,
                "list_unlinked_assets",
                new=AsyncMock(return_value=[candidate, other_series]),
            ),
        ):
            result = await wialon_units.suggest_wialon_asset_links(
                object(), "unit-1", master_section_id=None
            )
        self.assertEqual([item.asset_id for item in result.items], [candidate.id])
        self.assertEqual(result.items[0].matched_numbers, [3183])

    async def test_patch_can_unlink_and_rebaselines_counter_state(self):
        asset = SimpleNamespace(
            id=uuid4(),
            gtk_id=None,
            asset_type="locomotive",
            wialon_id="unit-1",
            model_id=None,
            updated_at=None,
        )
        db = SimpleNamespace(refresh=AsyncMock())
        with (
            patch.object(
                assets,
                "_get_scoped_asset",
                new=AsyncMock(return_value=asset),
            ),
            patch.object(
                assets.asset_links_repository,
                "get_active",
                new=AsyncMock(
                    return_value=[
                        SimpleNamespace(source="wialon", external_id="unit-1")
                    ]
                ),
            ),
            patch.object(
                assets.asset_links_service,
                "unlink",
                new=AsyncMock(),
            ),
            patch.object(
                assets.wialon_counters_repository,
                "rebaseline",
                new=AsyncMock(),
            ) as rebaseline,
            patch.object(assets, "_commit", new=AsyncMock()),
            patch.object(assets, "asset_read", return_value=_fixed_asset_read()),
        ):
            await assets.update_fixed_asset(
                db,
                asset.id,
                FixedAssetUpdate(wialon_id=None),
            )

        self.assertIsNone(asset.wialon_id)
        self.assertIsNone(rebaseline.await_args.kwargs["cnm"])
        self.assertIsNone(rebaseline.await_args.kwargs["cneh"])
        rebaseline.assert_awaited_once()

    async def test_patch_link_uses_current_unit_as_new_baseline(self):
        observed_at = datetime.now(timezone.utc)
        asset = SimpleNamespace(
            id=uuid4(),
            gtk_id=None,
            asset_type="locomotive",
            wialon_id=None,
            model_id=None,
            updated_at=None,
        )
        unit = SimpleNamespace(
            name="ТЭМ 1234",
            cnm=Decimal("1234.5"),
            cneh=Decimal("80.25"),
            last_message_at=observed_at,
        )
        db = SimpleNamespace(refresh=AsyncMock())
        with (
            patch.object(
                assets,
                "_get_scoped_asset",
                new=AsyncMock(return_value=asset),
            ),
            patch.object(
                assets.asset_links_repository,
                "get_active",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                assets.asset_links_service,
                "link",
                new=AsyncMock(),
            ),
            patch.object(
                assets.wialon_units_repository,
                "get_unit_record",
                new=AsyncMock(return_value=unit),
            ),
            patch.object(
                assets.wialon_counters_repository,
                "rebaseline",
                new=AsyncMock(),
            ) as rebaseline,
            patch.object(assets, "_commit", new=AsyncMock()),
            patch.object(assets, "asset_read", return_value=_fixed_asset_read()),
        ):
            await assets.update_fixed_asset(
                db,
                asset.id,
                FixedAssetUpdate(wialon_id="unit-1"),
            )

        self.assertEqual(asset.wialon_id, "unit-1")
        self.assertEqual(rebaseline.await_args.kwargs["cnm"], Decimal("1234.5"))
        self.assertEqual(rebaseline.await_args.kwargs["cneh"], Decimal("80.25"))
        self.assertEqual(rebaseline.await_args.kwargs["at"], observed_at)


if __name__ == "__main__":
    unittest.main()
