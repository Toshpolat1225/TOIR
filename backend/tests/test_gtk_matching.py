import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.models.assets import FixedAsset
from app.schemas.assets import FixedAssetCreate, FixedAssetUpdate
from app.services import assets as assets_service
from app.services import gtk as gtk_service
from app.services import gtk_matching
from app.schemas.gtk import GtkLinkBatchRequest, GtkLinkItem


def _asset(name: str, *, asset_type: str = "locomotive", inv: str = "I-1"):
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        inv_number=inv,
        asset_type=asset_type,
        series=None,
        gtk_id=None,
    )


class GtkMatchingTests(unittest.TestCase):
    def test_normalization_and_series_examples(self):
        self.assertEqual(
            gtk_matching.normalize_token("ПЭ-2М 298"),
            gtk_matching.normalize_token("ПЭ2М 298"),
        )
        self.assertEqual(
            gtk_matching.normalize_token("PE-2M 298"),
            gtk_matching.normalize_token("ПЭ2М 298"),
        )
        self.assertEqual(
            gtk_matching.extract_series("Тяговый агрегат ПЭ2У"), "ПЭ-2У"
        )
        self.assertEqual(
            gtk_matching.extract_series("Тепловзо ТЭМ18ДМ"), "ТЭМ18ДМ"
        )
        self.assertEqual(
            gtk_matching.extract_vehicle_numbers(
                "ПЭ-2м 111 (353)", series="ПЭ-2м"
            ),
            frozenset({111}),
        )

    def test_locomotive_suggestion_requires_exact_unique_inventory_number(self):
        gtk = SimpleNamespace(
            gtk_id=1,
            name="Locomotive",
            model_name="ПЭ-2М",
            garage_number="298",
            inventory_number="I-1",
        )
        only_asset = _asset("ПЭ-2М 298", inv="I-1")
        report = gtk_matching.match_report("locomotive", [gtk], [only_asset])
        self.assertEqual(report[0]["level"], "high")
        self.assertEqual(report[0]["candidate_count"], 1)
        self.assertEqual(report[0]["signals"], ["inventory_number"])
        self.assertEqual(report[0]["suggestion"]["id"], only_asset.id)

        another_asset = _asset("ПЭ2М 298", inv="I-1")
        report = gtk_matching.match_report(
            "locomotive", [gtk], [only_asset, another_asset]
        )
        self.assertEqual(report[0]["level"], "ambiguous")
        self.assertEqual(report[0]["candidate_count"], 2)
        self.assertIsNone(report[0]["suggestion"])

        no_match = gtk_matching.match_report(
            "locomotive", [gtk], [_asset("ПЭ-2М 298", inv="I-2")]
        )
        self.assertEqual(no_match[0]["level"], "none")

    def test_locomotive_matching_does_not_use_names_or_partial_inventory(self):
        gtk = SimpleNamespace(
            gtk_id=1,
            name="ПЭ-2М 298",
            model_name="ПЭ-2М",
            garage_number="298",
            inventory_number="ABC-1",
        )
        self.assertEqual(
            gtk_matching.match_report(
                "locomotive", [gtk], [_asset("ПЭ-2М 298", inv="ABC-10")]
            )[0]["level"],
            "none",
        )
        self.assertEqual(
            gtk_matching.match_report(
                "locomotive", [gtk], [_asset("Unrelated", inv="WIALON-ABC-1")]
            )[0]["level"],
            "none",
        )

    def test_carriage_registration_and_train_membership_do_not_affect_match(self):
        carriages = [
            SimpleNamespace(gtk_id=1, reg_number="REG-1", inventory_number="W-1"),
            SimpleNamespace(gtk_id=2, reg_number="REG-1", inventory_number="W-2"),
            SimpleNamespace(gtk_id=3, reg_number="UNIQUE", inventory_number=None),
        ]
        self.assertEqual(
            gtk_matching.preferred_carriage_ids(carriages, {2}), {1}
        )
        report = gtk_matching.match_report(
            "carriage",
            carriages,
            [
                _asset("REG-1", asset_type="wagon", inv="W-1"),
                _asset("REG-1", asset_type="wagon", inv="W-2"),
            ],
        )
        self.assertEqual(
            [row["level"] for row in report], ["high", "high", "none"]
        )

    def test_exact_inventory_duplicates_are_ambiguous_without_asset_selection(self):
        gtk = SimpleNamespace(gtk_id=1, inventory_number="W-1")
        report = gtk_matching.match_report(
            "carriage",
            [gtk],
            [
                _asset("Wagon 1", asset_type="wagon", inv="W-1"),
                _asset("Wagon 2", asset_type="wagon", inv="W-1"),
            ],
        )
        self.assertEqual(report[0]["level"], "ambiguous")
        self.assertEqual(report[0]["candidate_count"], 2)
        self.assertIsNone(report[0]["suggestion"])

    def test_empty_inventory_and_already_linked_records_have_no_suggestion(self):
        asset = _asset("Wagon", asset_type="wagon", inv="W-1")
        rows = [
            SimpleNamespace(gtk_id=1, inventory_number=" "),
            SimpleNamespace(gtk_id=2, inventory_number="W-1"),
            SimpleNamespace(gtk_id=3, inventory_number="W-1"),
        ]
        report = gtk_matching.match_report(
            "carriage",
            rows,
            [asset],
            linked_asset_ids={asset.id},
            linked_gtk_ids={3},
        )
        self.assertEqual(
            [item["level"] for item in report], ["none", "none", "none"]
        )
        self.assertTrue(all(item["suggestion"] is None for item in report))

    def test_carriage_duplicates_without_train_use_stable_id_tiebreak(self):
        carriages = [
            SimpleNamespace(gtk_id=1, reg_number="REG-1"),
            SimpleNamespace(gtk_id=2, reg_number="REG-1"),
        ]
        self.assertEqual(
            gtk_matching.preferred_carriage_ids(carriages, set()), {2}
        )
        self.assertEqual(
            gtk_service._suggestion(
                {"level": "duplicate", "candidate_count": 0}
            )["level"],
            "none",
        )


class GtkInventoryProposalTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_confirmation_keeps_the_existing_link(self):
        asset = _asset("Wagon", asset_type="wagon", inv="W-1")
        asset.gtk_id = "8"
        gtk_object = SimpleNamespace(
            gtk_id=8, name="GTK wagon", inventory_number="W-1"
        )
        current_link = SimpleNamespace(
            external_id="8", external_name=None, id=uuid4()
        )

        class Result:
            def scalar_one_or_none(self):
                return asset

        db = SimpleNamespace(
            execute=AsyncMock(return_value=Result()),
            commit=AsyncMock(),
            rollback=AsyncMock(),
        )
        payload = GtkLinkBatchRequest(
            links=[
                {
                    "asset_id": str(asset.id),
                    "gtk_id": 8,
                    "kind": "carriage",
                    "expected_inventory_number": "W-1",
                }
            ]
        )
        with (
            patch.object(
                gtk_service.repository,
                "list_assets_by_ids",
                new=AsyncMock(return_value={asset.id: asset}),
            ),
            patch.object(
                gtk_service.repository,
                "list_gtk_objects",
                new=AsyncMock(return_value={8: gtk_object}),
            ),
            patch.object(
                gtk_service.repository,
                "get_asset_for_update",
                new=AsyncMock(return_value=asset),
            ),
            patch.object(
                gtk_service.repository,
                "get_gtk_object_for_update",
                new=AsyncMock(return_value=gtk_object),
            ),
            patch.object(
                gtk_service.repository,
                "get_linked_assets_for_update",
                new=AsyncMock(return_value={"8": asset}),
            ),
            patch.object(
                gtk_service.repository,
                "list_assets_by_inventory",
                new=AsyncMock(return_value=[asset]),
            ),
            patch.object(
                gtk_service.asset_links_repository,
                "get_active_for_update",
                new=AsyncMock(return_value=current_link),
            ),
            patch.object(
                gtk_service.asset_links_service.repository,
                "find_active",
                new=AsyncMock(return_value=(current_link, asset)),
            ),
            patch.object(
                gtk_service.asset_links_service.repository,
                "add",
                new=AsyncMock(),
            ) as add_link,
            patch.object(
                gtk_service.asset_links_service.gtk_repository,
                "gtk_kind",
                new=AsyncMock(return_value="carriage"),
            ),
        ):
            self.assertEqual(await gtk_service.save_links(db, payload), 1)
            self.assertEqual(await gtk_service.save_links(db, payload), 1)

        add_link.assert_not_awaited()
        self.assertEqual(asset.gtk_id, "8")
        self.assertEqual(db.commit.await_count, 2)

    async def test_confirmation_rechecks_exact_unique_inventory_number(self):
        asset = _asset("Wagon", asset_type="wagon", inv="W-1")
        link = GtkLinkItem(
            asset_id=asset.id,
            gtk_id=8,
            kind="carriage",
            expected_inventory_number="W-1",
        )
        gtk_object = SimpleNamespace(inventory_number="W-1")
        with patch.object(
            gtk_service.repository,
            "list_assets_by_inventory",
            new=AsyncMock(return_value=[asset]),
        ):
            await gtk_service._validate_inventory_proposal(
                object(), link, asset, gtk_object
            )

    async def test_confirmation_rejects_stale_or_ambiguous_inventory(self):
        asset = _asset("Wagon", asset_type="wagon", inv="W-1")
        link = GtkLinkItem(
            asset_id=asset.id,
            gtk_id=8,
            kind="carriage",
            expected_inventory_number="W-1",
        )
        with patch.object(
            gtk_service.repository,
            "list_assets_by_inventory",
            new=AsyncMock(return_value=[asset]),
        ) as find_matches:
            with self.assertRaises(HTTPException) as stale:
                await gtk_service._validate_inventory_proposal(
                    object(),
                    link,
                    asset,
                    SimpleNamespace(inventory_number="W-2"),
                )
            self.assertEqual(stale.exception.status_code, 409)
            find_matches.assert_not_awaited()

            with patch.object(
                gtk_service.repository,
                "list_assets_by_inventory",
                new=AsyncMock(return_value=[asset, _asset("Duplicate", asset_type="wagon", inv="W-1")]),
            ):
                with self.assertRaises(HTTPException) as ambiguous:
                    await gtk_service._validate_inventory_proposal(
                        object(),
                        link,
                        asset,
                        SimpleNamespace(inventory_number="W-1"),
                    )
            self.assertEqual(ambiguous.exception.status_code, 409)

    def test_confirmation_never_replaces_an_existing_gtk_link(self):
        asset = _asset("Wagon", asset_type="wagon", inv="W-1")
        other_asset = _asset("Other wagon", asset_type="wagon", inv="W-2")
        link = GtkLinkItem(
            asset_id=asset.id,
            gtk_id=8,
            kind="carriage",
            expected_inventory_number="W-1",
        )
        with self.assertRaises(HTTPException) as object_conflict:
            gtk_service._validate_proposal_link_state(
                link, asset, {"8": other_asset}, None
            )
        self.assertEqual(object_conflict.exception.status_code, 409)

        with self.assertRaises(HTTPException) as asset_conflict:
            gtk_service._validate_proposal_link_state(
                link,
                asset,
                {},
                SimpleNamespace(external_id="9"),
            )
        self.assertEqual(asset_conflict.exception.status_code, 409)

        gtk_service._validate_proposal_link_state(
            link,
            asset,
            {"8": asset},
            SimpleNamespace(external_id="8"),
        )


class GtkLinkServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_fixed_asset_type_mismatch_is_422(self):
        with patch.object(
            assets_service.gtk_repository,
            "gtk_kind",
            new=AsyncMock(return_value="carriage"),
        ):
            with self.assertRaises(HTTPException) as raised:
                await assets_service._validate_gtk_link(
                    object(), "1", "locomotive"
                )
        self.assertEqual(raised.exception.status_code, 422)

    async def test_duplicate_gtk_id_conflicts_with_409_on_asset_create_and_patch(self):
        duplicate_error = IntegrityError("duplicate", {}, Exception())
        create_db = SimpleNamespace(
            add=Mock(),
            flush=AsyncMock(),
            commit=AsyncMock(side_effect=duplicate_error),
            rollback=AsyncMock(),
        )
        with (
            patch.object(
                assets_service,
                "_validate_gtk_link",
                new=AsyncMock(),
            ),
            patch.object(
                assets_service.repository,
                "active_catalog_value_exists",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                assets_service.repository, "add_asset", new=AsyncMock()
            ),
            patch.object(
                assets_service.asset_links_service, "link", new=AsyncMock()
            ),
            patch.object(
                assets_service.gtk_repository,
                "gtk_kind",
                new=AsyncMock(return_value="locomotive"),
            ),
            patch.object(
                assets_service.gtk_repository,
                "get_locomotive",
                new=AsyncMock(return_value=SimpleNamespace(name="GTK locomotive")),
            ),
            patch.object(
                assets_service.gtk_repository,
                "reset_locomotive_mileage_checkpoint",
                new=AsyncMock(),
            ),
            patch.object(
                assets_service.asset_passport,
                "prepare_new_asset",
                new=AsyncMock(
                    return_value={
                        "name": "Test locomotive",
                        "model_id": uuid4(),
                        "series": "ТЭМ18ДМ",
                        "number": "8",
                        "number_normalized": "8",
                    }
                ),
            ),
        ):
            with self.assertRaises(HTTPException) as create_error:
                await assets_service.create_fixed_asset(
                    create_db,
                    FixedAssetCreate(
                        inv_number="GTK-8",
                        name="Test locomotive",
                        asset_type="locomotive",
                        gtk_id="8",
                    ),
                )
        self.assertEqual(create_error.exception.status_code, 409)
        create_db.rollback.assert_awaited_once()

        asset = SimpleNamespace(
            id=uuid4(),
            gtk_id=None,
            asset_type="locomotive",
            wialon_id=None,
            model_id=None,
            updated_at=None,
        )
        patch_db = SimpleNamespace(
            commit=AsyncMock(side_effect=IntegrityError("duplicate", {}, Exception())),
            rollback=AsyncMock(),
        )
        with (
            patch.object(
                assets_service,
                "_get_scoped_asset",
                new=AsyncMock(return_value=asset),
            ),
            patch.object(
                assets_service,
                "_validate_gtk_link",
                new=AsyncMock(),
            ),
            patch.object(
                assets_service.asset_links_repository,
                "get_active",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                assets_service.asset_links_service,
                "link",
                new=AsyncMock(),
            ),
            patch.object(
                assets_service.gtk_repository,
                "gtk_kind",
                new=AsyncMock(return_value="locomotive"),
            ),
            patch.object(
                assets_service.gtk_repository,
                "get_locomotive",
                new=AsyncMock(return_value=SimpleNamespace(name="GTK loco")),
            ),
            patch.object(
                assets_service.gtk_repository,
                "reset_locomotive_mileage_checkpoint",
                new=AsyncMock(),
            ),
        ):
            with self.assertRaises(HTTPException) as patch_error:
                await assets_service.update_fixed_asset(
                    patch_db,
                    asset.id,
                    FixedAssetUpdate(gtk_id="8"),
                )
        self.assertEqual(patch_error.exception.status_code, 409)
        patch_db.rollback.assert_awaited_once()

    async def test_duplicate_gtk_id_conflict_rolls_back_whole_batch(self):
        asset_id = uuid4()
        asset = _asset("Wagon", asset_type="wagon")
        asset.id = asset_id
        asset.gtk_id = None
        carriage = SimpleNamespace(gtk_id=8, name="GTK carriage")
        async def rollback():
            asset.gtk_id = None

        db = SimpleNamespace(
            commit=AsyncMock(
                side_effect=IntegrityError("duplicate", {}, Exception())
            ),
            rollback=AsyncMock(side_effect=rollback),
        )
        request = GtkLinkBatchRequest(
            links=[{"asset_id": str(asset_id), "gtk_id": 8, "kind": "carriage"}]
        )
        with (
            patch.object(
                gtk_service.repository,
                "list_assets_by_ids",
                new=AsyncMock(return_value={asset_id: asset}),
            ),
            patch.object(
                gtk_service.repository,
                "list_gtk_objects",
                new=AsyncMock(return_value={8: carriage}),
            ),
            patch.object(
                gtk_service.repository,
                "get_linked_assets_for_update",
                new=AsyncMock(return_value={}),
            ),
            patch.object(
                gtk_service.repository,
                "gtk_kind",
                new=AsyncMock(return_value="carriage"),
            ),
            patch.object(
                gtk_service.asset_links_repository,
                "get_active_for_update",
                new=AsyncMock(return_value=None),
            ),
            patch.object(
                gtk_service.asset_links_service,
                "link",
                new=AsyncMock(
                    side_effect=HTTPException(
                        status_code=409, detail="Duplicate GTK link"
                    )
                ),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await gtk_service.save_links(db, request)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIsNone(asset.gtk_id)
        db.rollback.assert_awaited_once()

    async def test_individual_dry_run_does_not_write(self):
        carriage = SimpleNamespace(
            gtk_id=12,
            name="  Car   12 ",
            model_name="Model",
            inventory_number="",
            is_active=True,
        )
        db = SimpleNamespace(add=Mock(), commit=AsyncMock())
        with (
            patch.object(
                gtk_service.repository,
                "get_carriage",
                new=AsyncMock(return_value=carriage),
            ),
            patch.object(
                gtk_service.repository,
                "get_linked_assets",
                new=AsyncMock(return_value={}),
            ),
            patch.object(
                gtk_service.repository,
                "inventory_number_exists",
                new=AsyncMock(return_value=False),
            ),
        ):
            result = await gtk_service.create_carriage_asset(
                db, 12, dry_run=True
            )
        self.assertEqual(result["would_create"], 1)
        self.assertEqual(result["items"][0]["asset"]["name"], "Car 12")
        self.assertEqual(result["items"][0]["asset"]["inv_number"], "GTK-12")
        db.add.assert_not_called()
        db.commit.assert_not_awaited()

    async def test_bulk_dry_run_reports_inactive_duplicate_linked_and_eligible(self):
        carriages = [
            SimpleNamespace(gtk_id=1, reg_number="DUP", is_active=True, name="A", model_name=None, inventory_number=""),
            SimpleNamespace(gtk_id=2, reg_number="DUP", is_active=True, name="B", model_name=None, inventory_number=""),
            SimpleNamespace(gtk_id=3, reg_number="INACTIVE", is_active=False, name="C", model_name=None, inventory_number=""),
            SimpleNamespace(gtk_id=4, reg_number="LINKED", is_active=True, name="D", model_name=None, inventory_number=""),
            SimpleNamespace(gtk_id=5, reg_number="UNIQUE", is_active=True, name=" E  5 ", model_name="M", inventory_number="INV-5"),
        ]
        linked_asset = _asset("Linked", asset_type="wagon")
        linked_asset.gtk_id = "4"
        db = SimpleNamespace(add=Mock(), commit=AsyncMock())
        with (
            patch.object(
                gtk_service.repository,
                "list_all_carriages",
                new=AsyncMock(
                    return_value=[
                        (carriage, carriage.gtk_id == 2) for carriage in carriages
                    ]
                ),
            ),
            patch.object(
                gtk_service.repository,
                "get_linked_assets",
                new=AsyncMock(return_value={"4": linked_asset}),
            ),
            patch.object(
                gtk_service.repository,
                "inventory_number_exists",
                new=AsyncMock(return_value=False),
            ),
        ):
            result = await gtk_service.create_carriage_assets(db, dry_run=True)

        by_id = {item["gtk_id"]: item for item in result["items"]}
        self.assertEqual(result["would_create"], 1)
        self.assertEqual(result["skipped"], 4)
        self.assertEqual(by_id[1]["reason"], "duplicate_reg_number")
        self.assertEqual(by_id[2]["reason"], "missing_model")
        self.assertEqual(by_id[3]["reason"], "inactive")
        self.assertEqual(by_id[4]["reason"], "already_linked")
        self.assertEqual(by_id[5]["asset"]["name"], "E 5")
        db.add.assert_not_called()
        db.commit.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
