import unittest
from pathlib import Path


class AnalyticsSqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.migration_sql = (
            Path(__file__).parents[1]
            / "alembic"
            / "versions"
            / "0003_analytics.sql"
        ).read_text(encoding="utf-8")

    def test_norm_deviation_and_overrun_use_normalized_work_order_items(self):
        self.assertIn(
            "JOIN work_order_items woi ON woi.repair_id = wor.id",
            self.migration_sql,
        )
        self.assertIn(
            "((woi.qty - nn.standard_quantity) / nn.standard_quantity * 100)",
            self.migration_sql,
        )
        self.assertIn("d.deviation_percent > 20", self.migration_sql)
        self.assertIn("total_norm_cost - total_cost", self.migration_sql)

    def test_scoped_analytics_view_exposes_section_id(self):
        work_type_view = self.migration_sql.split(
            "CREATE OR REPLACE VIEW work_type_efficiency AS", maxsplit=1
        )[1].split("CREATE OR REPLACE VIEW monthly_efficiency AS", maxsplit=1)[0]

        self.assertIn("es.section_id", work_type_view)
        self.assertIn("GROUP BY es.section_id", work_type_view)


if __name__ == "__main__":
    unittest.main()
