import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.services.wialon_quality import CounterState, Reading, Verdict, evaluate


class WialonQualityTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)

    def test_first_reading_sets_baseline(self):
        reading = Reading(Decimal("100"), Decimal("20"), self.now)

        result = evaluate(None, reading, now=self.now)

        self.assertEqual(result.mileage.verdict, Verdict.BASELINE)
        self.assertEqual(result.hours.verdict, Verdict.BASELINE)
        self.assertEqual(result.state.baseline_cnm, Decimal("100"))
        self.assertEqual(result.state.baseline_cneh, Decimal("20"))

    def test_valid_deltas_are_accepted(self):
        previous_at = self.now - timedelta(hours=1)
        state = CounterState(
            baseline_cnm=Decimal("100"),
            last_cnm=Decimal("100"),
            last_cnm_at=previous_at,
            baseline_cneh=Decimal("10"),
            last_cneh=Decimal("10"),
            last_cneh_at=previous_at,
        )
        reading = Reading(Decimal("110"), Decimal("11.5"), self.now)

        result = evaluate(state, reading, now=self.now)

        self.assertEqual(result.mileage.verdict, Verdict.ACCEPTED)
        self.assertEqual(result.mileage.delta, Decimal("10"))
        self.assertEqual(result.hours.verdict, Verdict.ACCEPTED)
        self.assertEqual(result.hours.delta, Decimal("1.5"))
        self.assertEqual(result.state.last_cnm, Decimal("110"))
        self.assertEqual(result.state.last_cneh, Decimal("11.5"))

    def test_large_cnm_jump_is_rejected(self):
        state = CounterState(last_cnm=Decimal("100"), last_cnm_at=self.now - timedelta(hours=1))
        result = evaluate(
            state,
            Reading(Decimal("300"), None, self.now),
            now=self.now,
        )

        self.assertEqual(result.mileage.verdict, Verdict.REJECTED)
        self.assertEqual(result.state.last_cnm, Decimal("100"))

    def test_cnm_decrease_over_one_kilometer_is_rejected(self):
        state = CounterState(last_cnm=Decimal("100"), last_cnm_at=self.now - timedelta(hours=1))
        result = evaluate(
            state,
            Reading(Decimal("98.99"), None, self.now),
            now=self.now,
        )

        self.assertEqual(result.mileage.verdict, Verdict.REJECTED)
        self.assertEqual(result.state.last_cnm, Decimal("100"))

    def test_cnm_decrease_of_one_kilometer_is_unchanged(self):
        state = CounterState(last_cnm=Decimal("100"), last_cnm_at=self.now - timedelta(hours=1))
        result = evaluate(
            state,
            Reading(Decimal("99"), None, self.now),
            now=self.now,
        )

        self.assertEqual(result.mileage.verdict, Verdict.UNCHANGED)
        self.assertEqual(result.state.last_cnm, Decimal("100"))
        self.assertEqual(result.state.last_cnm_at, self.now)

    def test_zero_cneh_is_no_data_without_previous_counter(self):
        result = evaluate(
            None,
            Reading(None, Decimal("0"), self.now),
            now=self.now,
        )

        self.assertEqual(result.hours.verdict, Verdict.NO_DATA)
        self.assertIsNone(result.state.baseline_cneh)
        self.assertIsNone(result.state.last_cneh)

    def test_reading_older_than_24_hours_is_stale(self):
        stale_at = self.now - timedelta(hours=25)
        result = evaluate(
            None,
            Reading(Decimal("100"), Decimal("10"), stale_at),
            now=self.now,
        )

        self.assertEqual(result.mileage.verdict, Verdict.STALE)
        self.assertEqual(result.hours.verdict, Verdict.STALE)
        self.assertEqual(result.state, CounterState())

    def test_hilux_absolute_counter_is_suspect(self):
        result = evaluate(
            None,
            Reading(Decimal("1007343489"), Decimal("0"), self.now),
            now=self.now,
        )

        self.assertTrue(result.suspect_absolute)


if __name__ == "__main__":
    unittest.main()
