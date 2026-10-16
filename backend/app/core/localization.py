from typing import Annotated, Literal

from fastapi import Header

Locale = Literal["uz-Latn", "uz-Cyrl", "ru"]
SUPPORTED_LOCALES = ("uz-Latn", "uz-Cyrl", "ru")


def parse_locale(value: str | None) -> Locale:
    if value:
        for part in value.split(","):
            language = part.split(";", 1)[0].strip()
            if language in SUPPORTED_LOCALES:
                return language  # type: ignore[return-value]
    return "ru"


async def get_locale(accept_language: Annotated[str | None, Header()] = None) -> Locale:
    return parse_locale(accept_language)
