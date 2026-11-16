"""The unmatched Wialon units list must be buildable (a local import once made it raise UnboundLocalError -> HTTP 500)."""
from types import SimpleNamespace

from app.services.asset_matching import _to_source_object


def test_a_wialon_unit_becomes_a_source_object_with_its_classified_type():
    record = SimpleNamespace(unit_id="12345", name="МПЭ-2у 1234")
    source_object = _to_source_object("wialon", record)
    assert source_object.source == "wialon" and source_object.external_id == "12345"
    assert source_object.type == "locomotive"
    assert _to_source_object("wialon", SimpleNamespace(unit_id="7", name="ТЭМ2 3145")).type == "diesel"


def test_a_wialon_unit_of_an_unknown_kind_has_no_type():
    source_object = _to_source_object("wialon", SimpleNamespace(unit_id="9", name="Грузовик 5"))
    assert source_object.type is None
