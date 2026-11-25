"""Migration journal: import, journal-only recording, correcting and rolling back values (needs the pg test database)."""
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.core.database import SessionFactory
from app.core.timeutil import today_local
from app.models.assets import FixedAsset
from app.models.data_migration import DataMigrationBatch, DataMigrationItem
from app.models.identity import User
from app.services import data_migration as service
from app.services import data_migration_import as importer
from user_factory import ad_user

pytestmark = [pytest.mark.pg, pytest.mark.asyncio]


class World:
    def __init__(self):
        self.tag = uuid4().hex[:8]
        self.inv_a, self.inv_b, self.inv_dup = f"DM-A-{self.tag}", f"DM-B-{self.tag}", f"DM-D-{self.tag}"
        self.ids: dict[str, object] = {}
        self.user_id = uuid4()

    async def seed(self):
        async with SessionFactory() as db:
            db.add(User(id=self.user_id, email=f"dm-{self.tag}@example.test", full_name="DM Tester", role="admin", **ad_user()))
            for key, inv, serial in (("a", self.inv_a, "1"), ("b", self.inv_b, "2"), ("d1", self.inv_dup, "00018468"), ("d2", self.inv_dup, "00018497")):
                asset_id = uuid4()
                self.ids[key] = asset_id
                db.add(FixedAsset(id=asset_id, inv_number=inv, serial_number=serial, asset_type="wagon", status="operational", mileage=Decimal("0")))
            await db.commit()
        return self

    async def asset_date(self, key):
        async with SessionFactory() as db:
            return (await db.get(FixedAsset, self.ids[key])).last_maint_date

    def user(self):
        return User(id=self.user_id, email="x", full_name="DM Tester", role="admin")

    async def cleanup(self):
        async with SessionFactory() as db:
            await db.execute(delete(DataMigrationBatch).where(DataMigrationBatch.name.like(f"%{self.tag}%")))
            await db.execute(delete(FixedAsset).where(FixedAsset.id.in_(list(self.ids.values()))))
            await db.execute(delete(User).where(User.id == self.user_id))
            await db.commit()


async def _import(w, rows, *, commit=True, record_only=False, name=None):
    async with SessionFactory() as db:
        return await importer.import_rows(
            db, rows, batch_name=name or f"B {w.tag}", source_file=f"f-{w.tag}.xlsx", field="last_maint_date", record_only=record_only, commit=commit
        )


async def _items(w, batch_id):
    async with SessionFactory() as db:
        items, total = await service.list_items(db, batch_id, limit=100)
    return items, total


@pytest_asyncio.fixture
async def world():
    w = await World().seed()
    yield w
    await w.cleanup()


async def test_dry_run_writes_nothing_and_apply_writes_assets_and_journal_together(world):
    rows = [{"inv": world.inv_a, "date": "2026-11-12", "raw": "12.11.26"}, {"inv": world.inv_b, "date": "2026-10-01", "raw": "01.10.2026"}]
    dry = await _import(world, rows, commit=False)
    assert dry["to_journal"] == 2 and "batch_id" not in dry
    assert await world.asset_date("a") is None
    done = await _import(world, rows)
    assert done["written_to_assets"] == 2
    assert await world.asset_date("a") == date(2026, 11, 12)
    items, total = await _items(world, done["batch_id"])
    assert total == 2 and {i["raw_value"] for i in items} == {"12.11.26", "01.10.2026"}
    assert all(i["old_value"] is None and i["status"] == "applied" and i["current_value"] == i["new_value"] for i in items)
    with pytest.raises(ValueError):  # the same file twice is refused
        await _import(world, rows)


async def test_an_inventory_number_shared_by_two_assets_is_matched_by_serial_and_otherwise_refused(world):
    ok = await _import(world, [{"inv": world.inv_dup, "serial": "18468", "date": "2026-09-15"}, {"inv": world.inv_dup, "serial": "18497", "date": "2026-08-25"}])
    assert ok["to_journal"] == 2 and not ok["ambiguous"]
    assert await world.asset_date("d1") == date(2026, 9, 15) and await world.asset_date("d2") == date(2026, 8, 25)
    amb = await _import(world, [{"inv": world.inv_dup, "date": "2026-01-01"}], name=f"Other {world.tag}")
    assert amb["to_journal"] == 0 and len(amb["ambiguous"]) == 1


async def test_bad_future_missing_and_already_filled_rows_are_reported_not_written(world):
    async with SessionFactory() as db:
        (await db.get(FixedAsset, world.ids["b"])).last_maint_date = date(2025, 5, 5)
        await db.commit()
    future = (today_local() + timedelta(days=3)).isoformat()
    report = await _import(world, [
        {"inv": world.inv_a, "date": future}, {"inv": "NOPE-" + world.tag, "date": "2026-01-01"}, {"inv": world.inv_b, "date": "2026-02-02"}, {"inv": world.inv_a, "date": "not a date"},
    ])
    assert len(report["bad_value"]) == 2 and len(report["not_found"]) == 1 and len(report["already_has_other_value"]) == 1
    assert report["to_journal"] == 0 and await world.asset_date("b") == date(2025, 5, 5)  # an existing value is never overwritten


async def test_record_only_journals_values_already_in_the_asset_and_rejects_a_mismatch(world):
    async with SessionFactory() as db:
        (await db.get(FixedAsset, world.ids["a"])).last_maint_date = date(2026, 11, 12)
        (await db.get(FixedAsset, world.ids["b"])).last_maint_date = date(2026, 1, 1)
        await db.commit()
    report = await _import(world, [{"inv": world.inv_a, "date": "2026-11-12"}, {"inv": world.inv_b, "date": "2026-02-02"}], record_only=True)
    assert report["to_journal"] == 1 and len(report["mismatch_with_asset"]) == 1 and report["written_to_assets"] == 0
    assert await world.asset_date("b") == date(2026, 1, 1)


async def test_edit_changes_the_asset_and_the_journal_but_refuses_future_dates_and_values_changed_elsewhere(world):
    done = await _import(world, [{"inv": world.inv_a, "date": "2026-11-12", "raw": "12.11.26"}])
    items, _ = await _items(world, done["batch_id"])
    item_id = items[0]["id"]
    async with SessionFactory() as db:
        updated = await service.update_item(db, item_id, "2026-11-10", world.user())
    assert updated["new_value"] == "2026-11-10" and await world.asset_date("a") == date(2026, 11, 10)
    async with SessionFactory() as db:
        with pytest.raises(HTTPException) as future:
            await service.update_item(db, item_id, (today_local() + timedelta(days=1)).isoformat(), world.user())
        assert future.value.status_code == 422
        with pytest.raises(HTTPException) as bad:
            await service.update_item(db, item_id, "10.11.2026", world.user())
        assert bad.value.status_code == 422
    async with SessionFactory() as db:  # somebody changes the asset by another route
        (await db.get(FixedAsset, world.ids["a"])).last_maint_date = date(2026, 11, 20)
        await db.commit()
    async with SessionFactory() as db:
        with pytest.raises(HTTPException) as changed:
            await service.update_item(db, item_id, "2026-11-01", world.user())
        assert changed.value.status_code == 409
    async with SessionFactory() as db:
        with pytest.raises(HTTPException) as changed2:
            await service.revert_item(db, item_id, world.user())
        assert changed2.value.status_code == 409
    assert await world.asset_date("a") == date(2026, 11, 20)  # never overwritten


async def test_revert_item_restores_the_old_value_and_cannot_be_done_twice(world):
    done = await _import(world, [{"inv": world.inv_a, "date": "2026-11-12"}])
    items, _ = await _items(world, done["batch_id"])
    async with SessionFactory() as db:
        await service.revert_item(db, items[0]["id"], world.user())
    assert await world.asset_date("a") is None
    after, _ = await _items(world, done["batch_id"])
    assert after[0]["status"] == "reverted"
    async with SessionFactory() as db:
        with pytest.raises(HTTPException) as again:
            await service.revert_item(db, items[0]["id"], world.user())
        assert again.value.status_code == 409
        with pytest.raises(HTTPException) as edit:
            await service.update_item(db, items[0]["id"], "2026-01-01", world.user())
        assert edit.value.status_code == 409


async def test_revert_batch_skips_what_changed_elsewhere_and_counts_everything(world):
    done = await _import(world, [{"inv": world.inv_a, "date": "2026-11-12"}, {"inv": world.inv_b, "date": "2026-10-01"}])
    async with SessionFactory() as db:
        (await db.get(FixedAsset, world.ids["b"])).last_maint_date = date(2026, 10, 5)
        await db.commit()
    async with SessionFactory() as db:
        result = await service.revert_batch(db, UUID(done["batch_id"]), world.user())
    assert result == {"reverted": 1, "skipped_changed_elsewhere": 1, "already_reverted": 0}
    assert await world.asset_date("a") is None and await world.asset_date("b") == date(2026, 10, 5)
    async with SessionFactory() as db:
        batches = [b for b in await service.list_batches(db) if str(b["id"]) == done["batch_id"]]
    assert batches[0]["total"] == 2 and batches[0]["applied"] == 1 and batches[0]["reverted"] == 1


async def test_listing_filters_sorts_by_a_whitelist_and_unknown_batches_are_404(world):
    done = await _import(world, [{"inv": world.inv_a, "date": "2026-11-12", "raw": "x1"}, {"inv": world.inv_b, "date": "2026-10-01", "raw": "x2"}])
    bid = UUID(done["batch_id"])
    async with SessionFactory() as db:
        found, total = await service.list_items(db, bid, q=world.inv_b)
        assert total == 1 and found[0]["inv_number"] == world.inv_b
        ordered, _ = await service.list_items(db, bid, sort_by="new_value", sort_dir="desc")
        assert [i["new_value"] for i in ordered] == ["2026-11-12", "2026-10-01"]
        with pytest.raises(HTTPException) as bad_sort:
            await service.list_items(db, bid, sort_by="asset_id; drop table x")
        assert bad_sort.value.status_code == 422
        with pytest.raises(HTTPException) as missing:
            await service.list_items(db, uuid4())
        assert missing.value.status_code == 404


async def test_a_fully_reverted_batch_can_be_loaded_again_and_stays_as_history(world):
    rows = [{"inv": world.inv_a, "date": "2026-11-12"}]
    first = await _import(world, rows)
    async with SessionFactory() as db:
        await service.revert_batch(db, UUID(first["batch_id"]), world.user())
    assert await world.asset_date("a") is None
    dry = await _import(world, rows, commit=False)  # a dry run must not rename anything
    assert dry["to_journal"] == 1
    second = await _import(world, rows)
    assert second["written_to_assets"] == 1 and second["batch_id"] != first["batch_id"]
    assert await world.asset_date("a") == date(2026, 11, 12)
    async with SessionFactory() as db:
        names = {str(b["id"]): b["name"] for b in await service.list_batches(db)}
    assert names[first["batch_id"]].endswith("]") and "отменён" in names[first["batch_id"]] and names[second["batch_id"]] == f"B {world.tag}"
    with pytest.raises(ValueError):  # the live batch still blocks a third load
        await _import(world, rows)
