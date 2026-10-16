import math
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.services import ml


class MlCalculationTests(unittest.TestCase):
    def test_consumption_anomaly_uses_repair_history(self):
        finding = ml.detect_consumption_anomaly(
            Decimal("30"),
            [Decimal("10"), Decimal("11"), Decimal("12")],
        )

        self.assertIsNotNone(finding)
        assert finding is not None
        self.assertEqual(finding["severity"], "critical")
        self.assertGreater(finding["z_score"], 2)
        self.assertGreater(finding["deviation_percent"], 30)
        self.assertEqual(finding["probability"], 1)

    def test_linear_regression_predicts_next_observation(self):
        self.assertEqual(ml.linear_regression_predict([10, 20, 30]), 40)

    def test_consumption_deviation_alone_triggers_anomaly(self):
        finding = ml.detect_consumption_anomaly(
            Decimal("140"),
            [Decimal("0"), Decimal("100"), Decimal("200")],
        )

        self.assertIsNotNone(finding)
        assert finding is not None
        self.assertLessEqual(finding["z_score"], 2)
        self.assertGreater(abs(finding["deviation_percent"]), 30)

    def test_rul_probability_and_low_remaining_mileage_are_calculated(self):
        first = datetime(2026, 1, 1, tzinfo=timezone.utc)
        dates = [first + timedelta(days=30 * index) for index in range(4)]
        samples = [
            (first + timedelta(days=10 * index), Decimal(8000 + 1000 * index))
            for index in range(3)
        ]

        prediction = ml.predict_failure(
            dates,
            samples,
            Decimal("10000"),
            today=(dates[-1] + timedelta(days=30)).date(),
        )

        self.assertIsNotNone(prediction)
        assert prediction is not None
        self.assertAlmostEqual(
            prediction["probability"], 1 - math.exp(-1), places=6
        )
        self.assertEqual(prediction["predicted_failure_km"], 10000)
        self.assertEqual(prediction["severity"], "critical")

    def test_health_score_applies_all_penalties(self):
        self.assertEqual(ml.calculate_health_score(0.2, 5, 90), 45)


class MlHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_insufficient_history_does_not_add_insight(self):
        order = SimpleNamespace(
            id=uuid4(),
            section_id=uuid4(),
            closed_at=datetime.now(timezone.utc),
        )
        asset = SimpleNamespace(
            id=uuid4(),
            mileage=Decimal("100"),
            last_maint_date=None,
        )
        bundle = {
            "order": order,
            "asset": asset,
            "repairs": [
                {
                    "work_type_id": uuid4(),
                    "work_type_code": "ТО-1",
                    "quantity": Decimal("10"),
                }
            ],
        }
        db = SimpleNamespace(add=Mock(), flush=AsyncMock())

        with (
            patch.object(
                ml.repository,
                "get_anomaly_history",
                new=AsyncMock(return_value=[Decimal("1"), Decimal("2")]),
            ),
            patch.object(
                ml.repository,
                "list_maintenance_events",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                ml.repository,
                "list_mileage_samples",
                new=AsyncMock(return_value=[]),
            ),
        ):
            result = await ml._analyze_asset(db, asset, bundle)

        self.assertEqual(result, (0, 0))
        db.add.assert_not_called()
        db.flush.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
