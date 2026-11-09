from typing import Literal

Locale = Literal["ru"]
SUPPORTED_LOCALES = ("ru",)


def parse_locale(_value: str | None = None) -> Locale:
    return "ru"


async def get_locale() -> Locale:
    return "ru"
