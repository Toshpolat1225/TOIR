import unittest

from app.services.wialon_asset_import import (
    classify_asset_type,
    extract_asset_series,
)


class WialonAssetImportTests(unittest.TestCase):
    def test_asset_type_prefixes(self):
        cases = (
            ("ПЭ-2у 094", "locomotive"),
            ("МПЭ-2у 001", "locomotive"),
            ("ТЭМ18 ДМ 3183", "diesel"),
            ("2тэ116", "diesel"),
            ("КамАЗ", None),
            ("Nexia", None),
        )
        for name, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(classify_asset_type(name), expected)

    def test_series_extraction(self):
        cases = (
            ("ПЭ-2у 094", "ПЭ-2у"),
            ("МПЭ-2у 001", "МПЭ-2у"),
            ("ТЭМ18 ДМ 3183", "ТЭМ18 ДМ"),
            ("2тэ116", "2ТЭ116"),
            ("2tэ116 004", "2ТЭ116"),
            ("КамАЗ", None),
            ("Nexia", None),
        )
        for name, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(extract_asset_series(name), expected)

    def test_type_matching_is_case_insensitive_for_cyrillic_and_latin(self):
        self.assertEqual(classify_asset_type("пэ-2у"), "locomotive")
        self.assertEqual(classify_asset_type("mpe-2y 001"), "locomotive")
        self.assertEqual(classify_asset_type("tem18 dm 3183"), "diesel")
        self.assertEqual(classify_asset_type("TЭМ18 ДМ 3183"), "diesel")
        self.assertEqual(classify_asset_type("2tэ116"), "diesel")


if __name__ == "__main__":
    unittest.main()
