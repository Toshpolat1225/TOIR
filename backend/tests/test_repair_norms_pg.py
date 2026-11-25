"""Repair consumption norms: quantity parsing, import (dry-run first), and correcting the lines (needs the pg test database)."""
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import delete, select

from app.core.database import SessionFactory
from app.models.asset_models import AssetModel
from app.models.identity import User
from app.models.maintenance import WorkType
from app.models.repair_norms import RepairNormItem
from app.schemas.repair_norms import RepairNormItemCreate, RepairNormItemUpdate
from app.services import repair_norms as service
from user_factory import ad_user


def test_the_first_number_of_the_source_text_is_the_quantity():
    cases = {"1200": "1200", "12/1,44-2,4": "12", "20./5": "20", "0,1/0,2": "0.1", "10/15-16,6-18,6": "10", "2,5/6-7,27": "2.5", "  8 ": "8"}
    for text, expected in cases.items():
        assert service.parse_quantity(text) == Decimal(expected), text
    assert service.parse_quantity("по необходимости") is None and service.parse_quantity("") is None


def test_units_are_unified_but_compound_units_stay():
    assert [service.normalize_unit(u) for u in ("дона", "шт", "шт.", "жамланма", "кг", "дона/кг", " м/кг ", "", None)] == [
        "шт.", "шт.", "шт.", "компл.", "кг", "дона/кг", "м/кг", None, None]


def test_the_update_body_needs_a_field_and_refuses_unknown_ones():
    with pytest.raises(ValidationError):
        RepairNormItemUpdate()
    with pytest.raises(ValidationError):
        RepairNormItemUpdate(name="x", quantity=5)
    with pytest.raises(ValidationError):
        RepairNormItemUpdate(name=None)
    RepairNormItemUpdate(unit=None)


class World:
    def __init__(self):
        self.tag = uuid4().hex[:8]
        self.wt_id = uuid4()
        self.model_id = uuid4()
        self.user_id = uuid4()
        self.code = f"РН-{self.tag}"
        self.model_name = f"M-{self.tag}"

    async def seed(self):
        async with SessionFactory() as db:
            db.add(User(id=self.user_id, email=f"rn-{self.tag}@example.test", full_name="RN Tester", role="admin", **ad_user()))
            db.add(WorkType(id=self.wt_id, code=self.code, name=self.code, unit_type="wagon"))
            db.add(AssetModel(id=self.model_id, name=self.model_name, name_normalized=self.model_name.lower(), asset_type="wagon"))
            await db.commit()
        return self

    def user(self):
        return User(id=self.user_id, email="x", full_name="RN Tester", role="admin")

    def rows(self):
        return [
            {"seq": "1", "parent_seq": "", "section": "materials", "name": "Сталь лист δ 4", "unit": "кг", "quantity_text": "1200", "note": ""},
            {"seq": "2", "parent_seq": "1", "section": "materials", "name": "при замене на Сталь лист δ 3", "unit": "кг", "quantity_text": "890", "note": ""},
            {"seq": "3", "parent_seq": "", "section": "spare_parts", "name": "Болт М12", "unit": "дона/кг", "quantity_text": "12/1,44-2,4", "note": ""},
            {"seq": "4", "parent_seq": "", "section": "spare_parts", "name": "Тележка", "unit": "дона", "quantity_text": "1", "note": "Допускается"},
        ]

    async def cleanup(self):
        async with SessionFactory() as db:
            await db.execute(delete(RepairNormItem).where(RepairNormItem.work_type_id == self.wt_id))
            await db.execute(delete(WorkType).where(WorkType.id == self.wt_id))
            await db.execute(delete(AssetModel).where(AssetModel.id == self.model_id))
            await db.execute(delete(User).where(User.id == self.user_id))
            await db.commit()


@pytest_asyncio.fixture
async def world():
    w = await World().seed()
    yield w
    await w.cleanup()


async def _import(w, *, commit, rows=None, model=True):
    async with SessionFactory() as db:
        return await service.import_set(
            db, rows if rows is not None else w.rows(), work_type_code=w.code, asset_type="wagon", model_name=w.model_name if model else None,
            source_file="f.xls", source_sheet="2025", commit=commit,
        )


@pytest.mark.pg
@pytest.mark.asyncio
async def test_dry_run_writes_nothing_then_apply_links_alternatives_and_a_second_load_is_refused(world):
    dry = await _import(world, commit=False)
    assert dry["lines"] == 4 and dry["alternatives"] == 1 and not dry["bad_rows"]
    async with SessionFactory() as db:
        assert not [s for s in await service.list_sets(db) if s["work_type_code"] == world.code]  # a dry run wrote nothing
    done = await _import(world, commit=True)
    assert done["committed"] is True
    async with SessionFactory() as db:
        items, total = await service.list_items(db, world.wt_id, "wagon", world.model_id)
    assert total == 4 and [i.seq for i in items] == [1, 2, 3, 4]
    by = {i.seq: i for i in items}
    assert by[2].parent_id == by[1].id and by[1].parent_id is None and by[3].quantity == Decimal("12") and by[3].quantity_text == "12/1,44-2,4"
    assert by[3].unit == "дона/кг" and by[4].unit == "шт." and by[4].note == "Допускается" and by[1].source_file == "f.xls"
    with pytest.raises(ValueError):
        await _import(world, commit=True)  # never mixes two loads
    async with SessionFactory() as db:
        sets = [s for s in await service.list_sets(db) if s["work_type_code"] == world.code]
    assert sets[0]["total"] == 4 and sets[0]["materials"] == 2 and sets[0]["spare_parts"] == 2 and sets[0]["alternatives"] == 1 and sets[0]["model_name"] == world.model_name


@pytest.mark.pg
@pytest.mark.asyncio
async def test_unknown_repair_kind_or_model_and_broken_rows_are_reported(world):
    async with SessionFactory() as db:
        with pytest.raises(ValueError):
            await service.import_set(db, world.rows(), work_type_code="НЕТ-ТАКОГО", asset_type="wagon", model_name=None, source_file="f", source_sheet="s")
        with pytest.raises(ValueError):
            await service.import_set(db, world.rows(), work_type_code=world.code, asset_type="wagon", model_name="NO-SUCH-MODEL", source_file="f", source_sheet="s")
    bad = world.rows() + [{"seq": "x", "parent_seq": "", "section": "materials", "name": "n", "unit": "", "quantity_text": "1", "note": ""},
                          {"seq": "9", "parent_seq": "77", "section": "materials", "name": "child of nothing", "unit": "", "quantity_text": "1", "note": ""},
                          {"seq": "10", "parent_seq": "", "section": "materials", "name": "ИЧТБ начальник", "unit": "", "quantity_text": "Иванов И.И.", "note": ""}]
    report = await _import(world, commit=True, rows=bad)
    assert len(report["bad_rows"]) == 3  # a person's name in the quantity column is refused
    async with SessionFactory() as db:
        _, total = await service.list_items(db, world.wt_id, "wagon", world.model_id)
    assert total == 0  # one bad row stops the whole set: nothing is half-loaded


@pytest.mark.pg
@pytest.mark.asyncio
async def test_add_edit_and_delete_lines_with_checks(world):
    await _import(world, commit=True)
    async with SessionFactory() as db:
        items, _ = await service.list_items(db, world.wt_id, "wagon", world.model_id)
    main, child = items[0], items[1]
    async with SessionFactory() as db:
        added = await service.create_item(
            db, RepairNormItemCreate(work_type_id=world.wt_id, asset_type="wagon", asset_model_id=world.model_id, section="spare_parts", name=" Гайка М30 ", unit="шт", quantity_text="10./4"), world.user())
    assert added.seq == 5 and added.name == "Гайка М30" and added.quantity == Decimal("10") and added.unit == "шт."
    async with SessionFactory() as db:
        with pytest.raises(HTTPException) as nested:  # an alternative of an alternative is refused
            await service.create_item(db, RepairNormItemCreate(work_type_id=world.wt_id, asset_type="wagon", asset_model_id=world.model_id, name="x", quantity_text="1", parent_id=child.id), world.user())
        assert nested.value.status_code == 422
        with pytest.raises(HTTPException) as other_set:  # a parent from another norm set is refused
            await service.create_item(db, RepairNormItemCreate(work_type_id=world.wt_id, asset_type="wagon", asset_model_id=None, name="x", quantity_text="1", parent_id=main.id), world.user())
        assert other_set.value.status_code == 422
    async with SessionFactory() as db:
        changed = await service.update_item(db, main.id, RepairNormItemUpdate(quantity_text="1300", note="уточнено"), world.user())
    assert changed.quantity == Decimal("1300") and changed.quantity_text == "1300" and changed.note == "уточнено"
    async with SessionFactory() as db:
        await service.delete_item(db, main.id, world.user())  # its alternative goes with it
        remaining, total = await service.list_items(db, world.wt_id, "wagon", world.model_id)
    assert total == 3 and main.id not in {i.id for i in remaining} and child.id not in {i.id for i in remaining}  # 4 loaded + 1 added - the line and its alternative
    async with SessionFactory() as db:
        with pytest.raises(HTTPException) as gone:
            await service.update_item(db, main.id, RepairNormItemUpdate(name="x"), world.user())
        assert gone.value.status_code == 404
        removed = await service.delete_set(db, world.wt_id, "wagon", world.model_id, world.user())
        assert removed == 3


@pytest.mark.pg
@pytest.mark.asyncio
async def test_listing_filters_by_section_and_text_and_other_sets_stay_apart(world):
    await _import(world, commit=True)
    async with SessionFactory() as db:
        parts, total = await service.list_items(db, world.wt_id, "wagon", world.model_id, section="spare_parts")
        assert total == 2 and {p.name for p in parts} == {"Болт М12", "Тележка"}
        found, total = await service.list_items(db, world.wt_id, "wagon", world.model_id, q="болт")
        assert total == 1
        none, total = await service.list_items(db, world.wt_id, "wagon", None)  # the set without a model is another set
        assert total == 0 and none == []
        other, total = await service.list_items(db, world.wt_id, "tank_car", None)
        assert total == 0


@pytest.mark.pg
@pytest.mark.asyncio
async def test_series_groups_keep_sets_apart_and_carry_assembly_names_and_the_basis(world):
    rows = [
        {"seq": "1", "parent_seq": "", "section": "materials", "group_name": "", "name": "Ветошь", "unit": "кг", "quantity_text": "100", "note": ""},
        {"seq": "2", "parent_seq": "", "section": "spare_parts", "group_name": "Дизел цилиндр блоги", "name": "Гайка", "unit": "дона", "quantity_text": "14", "note": ""},
        {"seq": "3", "parent_seq": "", "section": "lubricants", "group_name": "", "name": "Масло И-20", "unit": "кг", "quantity_text": "430±20", "note": ""},
    ]
    async with SessionFactory() as db:
        a = await service.import_set(db, rows, work_type_code=world.code, asset_type="diesel", model_name=None, source_file="f", source_sheet="s",
                                     commit=True, norm_group="ТЭМ2, ТЭМ18", basis="per_repair")
        b = await service.import_set(db, rows[:1], work_type_code=world.code, asset_type="diesel", model_name=None, source_file="f", source_sheet="s",
                                     commit=True, norm_group="2ТЭ116", basis="per_month_per_unit")
    assert a["groups"] == 1 and a["lines"] == 3 and b["lines"] == 1 and b["basis"] == "per_month_per_unit"
    async with SessionFactory() as db:
        sets = {s["norm_group"]: s for s in await service.list_sets(db) if s["work_type_code"] == world.code}
        assert set(sets) == {"ТЭМ2, ТЭМ18", "2ТЭ116"}
        assert sets["ТЭМ2, ТЭМ18"]["lubricants"] == 1 and sets["ТЭМ2, ТЭМ18"]["spare_parts"] == 1 and sets["2ТЭ116"]["basis"] == "per_month_per_unit"
        items, total = await service.list_items(db, world.wt_id, "diesel", None, norm_group="ТЭМ2, ТЭМ18")
        assert total == 3 and [i.group_name for i in items] == [None, "Дизел цилиндр блоги", None]
        assert items[2].quantity == Decimal("430") and items[2].quantity_text == "430±20"
        other, total = await service.list_items(db, world.wt_id, "diesel", None, norm_group="2ТЭ116")
        assert total == 1
        none, total = await service.list_items(db, world.wt_id, "diesel", None)  # the set without a group is another set
        assert total == 0
        with pytest.raises(HTTPException) as mixed:  # one set cannot mix per-repair and per-month lines
            await service.create_item(db, RepairNormItemCreate(work_type_id=world.wt_id, asset_type="diesel", norm_group="2ТЭ116", basis="per_repair", name="x", quantity_text="1"), world.user())
        assert mixed.value.status_code == 422
        added = await service.create_item(db, RepairNormItemCreate(work_type_id=world.wt_id, asset_type="diesel", norm_group="2ТЭ116", basis="per_month_per_unit", section="lubricants", group_name="Узел", name="Смазка", quantity_text="2"), world.user())
        assert added.seq == 2 and added.group_name == "Узел" and added.section == "lubricants"
        assert await service.delete_set(db, world.wt_id, "diesel", None, world.user(), "2ТЭ116") == 2
        assert await service.delete_set(db, world.wt_id, "diesel", None, world.user(), "ТЭМ2, ТЭМ18") == 3
