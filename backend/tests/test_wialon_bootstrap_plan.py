import unittest
from decimal import Decimal
from types import SimpleNamespace

from app.services.wialon_bootstrap_plan import plan_bootstrap


def asset(asset_id, name, *, wialon_id=None, mileage=Decimal("100")):
    return SimpleNamespace(
        id=asset_id,
        name=name,
        wialon_id=wialon_id,
        mileage=mileage,
    )


def unit(unit_id, name):
    return SimpleNamespace(
        unit_id=unit_id,
        name=name,
        mileage=Decimal("120"),
        engine_hours=Decimal("25"),
    )


class WialonBootstrapPlanTests(unittest.TestCase):
    def test_existing_wialon_id_is_mapped(self):
        rows = plan_bootstrap(
            [unit("w-1", "Wialon name")],
            [asset("a-1", "TOIR name", wialon_id="w-1")],
            set(),
        )

        self.assertEqual([row.status for row in rows], ["mapped"])
        self.assertEqual(rows[0].asset_id, "a-1")

    def test_unique_exact_name_is_suggested(self):
        rows = plan_bootstrap(
            [unit("w-1", "  Lokomotiv   1 ")],
            [asset("a-1", "lokomotiv 1")],
            set(),
        )

        self.assertEqual(rows[0].status, "name_unique")
        self.assertEqual(rows[0].asset_id, "a-1")

    def test_duplicate_asset_names_are_ambiguous(self):
        rows = plan_bootstrap(
            [unit("w-1", "Lokomotiv 1")],
            [asset("a-1", "Lokomotiv 1"), asset("a-2", "Lokomotiv 1")],
            set(),
        )

        self.assertEqual(rows[0].status, "ambiguous")
        self.assertIsNone(rows[0].asset_id)

    def test_missing_name_match_is_unmapped(self):
        rows = plan_bootstrap(
            [unit("w-1", "Unknown")],
            [asset("a-1", "Different")],
            set(),
        )

        self.assertEqual(rows[0].status, "unmapped")

    def test_mapped_asset_without_unit_is_reported(self):
        rows = plan_bootstrap(
            [],
            [asset("a-1", "Lokomotiv 1", wialon_id="w-1")],
            set(),
        )

        self.assertEqual([row.status for row in rows], ["asset_without_unit"])
        self.assertEqual(rows[0].asset_id, "a-1")


if __name__ == "__main__":
    unittest.main()
