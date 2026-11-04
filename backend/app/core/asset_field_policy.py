from dataclasses import dataclass
from typing import Literal


FieldMode = Literal["auto_fill_if_empty", "suggest_only", "manual_only"]


@dataclass(frozen=True)
class AssetFieldPolicy:
    source: str
    mode: FieldMode | None


ASSET_FIELD_POLICY: dict[str, AssetFieldPolicy] = {
    "inv_number": AssetFieldPolicy("toir", "manual_only"),
    "org_unit_id": AssetFieldPolicy("toir", "manual_only"),
    "asset_type": AssetFieldPolicy("toir", "manual_only"),
    "accounting_inv_number": AssetFieldPolicy("onec", "suggest_only"),
    "commissioned_at": AssetFieldPolicy("onec", "suggest_only"),
    "serial_number": AssetFieldPolicy("onec", "suggest_only"),
    "year_built": AssetFieldPolicy("onec", "suggest_only"),
    "number": AssetFieldPolicy("gtk", "auto_fill_if_empty"),
    "model_id": AssetFieldPolicy("gtk", "auto_fill_if_empty"),
    "mileage": AssetFieldPolicy("wialon", None),
    "online": AssetFieldPolicy("wialon", None),
    "speed": AssetFieldPolicy("wialon", None),
}

PASSPORT_FIELD_NAMES = frozenset(
    field_name
    for field_name, policy in ASSET_FIELD_POLICY.items()
    if policy.mode is not None
)
