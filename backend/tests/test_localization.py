import unittest

from app.core.localization import parse_locale


class LocaleParsingTests(unittest.TestCase):
    def test_accepts_only_supported_locale_tags(self):
        self.assertEqual(parse_locale("uz-Latn"), "uz-Latn")
        self.assertEqual(parse_locale("uz-Cyrl"), "uz-Cyrl")
        self.assertEqual(parse_locale("ru"), "ru")

    def test_accept_language_uses_first_supported_language(self):
        self.assertEqual(parse_locale("en-US,en;q=0.9,uz-Cyrl;q=0.8"), "uz-Cyrl")

    def test_invalid_and_missing_values_fall_back_to_russian(self):
        self.assertEqual(parse_locale("uz"), "ru")
        self.assertEqual(parse_locale("xx, en-US"), "ru")
        self.assertEqual(parse_locale(None), "ru")


if __name__ == "__main__":
    unittest.main()
