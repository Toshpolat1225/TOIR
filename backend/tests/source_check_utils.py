import re


def without_locale_block(source: str, locale: str) -> str:
    pattern = re.compile(
        rf'(?ims)^  "{re.escape(locale)}": \{{\r?\n.*?^  \}},\r?\n'
    )
    result, count = pattern.subn("", source, count=1)
    if count != 1:
        raise AssertionError(f"Expected one {locale} translation block")
    if locale.lower() == "uz-cyrl":
        option_pattern = re.compile(
            r'(<option value="uz-cyrl">)[^<]*(</option>)', re.IGNORECASE
        )
        result, count = option_pattern.subn(r"\1\2", result, count=1)
        if count != 1:
            raise AssertionError("Expected the Uzbek Cyrillic locale selector")
    return result
