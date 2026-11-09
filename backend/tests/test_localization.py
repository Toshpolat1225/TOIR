import unittest

from app.core.localization import parse_locale
from app.schemas.asset_catalogs import AssetCatalogWrite


class LocaleParsingTests(unittest.TestCase):
    def test_always_uses_russian(self):
        self.assertEqual(parse_locale("ru"), "ru")
        self.assertEqual(parse_locale("uz-Latn"), "ru")
        self.assertEqual(parse_locale("uz-Cyrl"), "ru")
        self.assertEqual(parse_locale("en-US,en;q=0.9"), "ru")
        self.assertEqual(parse_locale("uz"), "ru")
        self.assertEqual(parse_locale("xx, en-US"), "ru")
        self.assertEqual(parse_locale(None), "ru")

    def test_asset_catalog_requires_only_russian_name(self):
        payload = AssetCatalogWrite(
            code="locomotive",
            names={"ru": "Локомотив"},
        )
        self.assertEqual(payload.names, {"ru": "Локомотив"})

        with self.assertRaises(ValueError):
            AssetCatalogWrite(
                code="locomotive",
                names={"uz-Latn": "Lokomotiv", "ru": "Локомотив"},
            )


if __name__ == "__main__":
    unittest.main()
