"""Integration filter of the assets page: every system combination is exact (needs pg_rehearse)."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.core.database import SessionFactory
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.gtk import GtkCarriage
from app.models.wialon_units import WialonUnitRecord
from app.services import unified_assets

pytestmark = [pytest.mark.pg, pytest.mark.asyncio]

NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)


async def _seed():
    tag = uuid4().hex[:8]
    gtk_base = 800_000_000 + (uuid4().int % 90_000_000) * 10
    ids = {k: uuid4() for k in ("toir", "toir_gtk", "both", "all3", "ended_gtk")}
    async with SessionFactory() as db:
        for key, asset_id in ids.items():
            db.add(FixedAsset(id=asset_id, inv_number=f"SRC-{key}-{tag}", asset_type="wagon",
                              status="operational"))
        await db.commit()
        db.add_all([
            WialonUnitRecord(unit_id=f"u-both-{tag}", name=f"SRC unit both {tag}"),
            WialonUnitRecord(unit_id=f"u-all3-{tag}", name=f"SRC unit all3 {tag}"),
            WialonUnitRecord(unit_id=f"u-only-{tag}", name=f"SRC unit only {tag}"),
            GtkCarriage(gtk_id=gtk_base + 1, name=f"SRC gtk linked {tag}", is_active=True),
            GtkCarriage(gtk_id=gtk_base + 2, name=f"SRC gtk linked2 {tag}", is_active=True),
            GtkCarriage(gtk_id=gtk_base + 3, name=f"SRC gtk orphan {tag}",
                        inventory_number=f"ORPH-{tag}", is_active=True),
            GtkCarriage(gtk_id=gtk_base + 4, name=f"SRC gtk ended {tag}", is_active=True),
        ])
        await db.commit()
        db.add_all([
            AssetSourceLink(asset_id=ids["toir_gtk"], source="gtk", external_id=str(gtk_base + 1)),
            AssetSourceLink(asset_id=ids["all3"], source="gtk", external_id=str(gtk_base + 2)),
            # an ENDED gtk link does not count as linked
            AssetSourceLink(asset_id=ids["ended_gtk"], source="gtk", external_id=str(gtk_base + 4),
                            status="ended"),
            AssetSourceLink(asset_id=ids["both"], source="wialon", external_id=f"u-both-{tag}"),
            AssetSourceLink(asset_id=ids["all3"], source="wialon", external_id=f"u-all3-{tag}"),
        ])
        await db.commit()
    return tag, ids, gtk_base


async def _cleanup(tag, ids, gtk_base):
    async with SessionFactory() as db:
        await db.execute(delete(AssetSourceLink).where(AssetSourceLink.asset_id.in_(list(ids.values()))))
        await db.execute(delete(FixedAsset).where(FixedAsset.id.in_(list(ids.values()))))
        await db.execute(delete(WialonUnitRecord).where(WialonUnitRecord.unit_id.like(f"u-%-{tag}")))
        await db.execute(delete(GtkCarriage).where(GtkCarriage.gtk_id.in_([gtk_base + i for i in range(1, 5)])))
        await db.commit()


async def _names(source, tag, **kwargs):
    async with SessionFactory() as db:
        items, total = await unified_assets.list_unified_assets(
            db, source=source, asset_type=kwargs.get("asset_type"), asset_status=None,
            section_id=None, master_section_id=kwargs.get("master_section_id"),
            q=f"SRC", limit=500, offset=0, sort_by="name", sort_order="asc",
        )
    items = [i for i in items if tag in (i.name or "") or tag in (i.inv_number or "")]
    return items, total


async def test_each_source_combination_returns_exactly_its_assets():
    tag, ids, gtk_base = await _seed()
    try:
        expected = {
            "toir": {f"SRC-toir-{tag}", f"SRC-ended_gtk-{tag}"},
            "toir_gtk": {f"SRC-toir_gtk-{tag}"},
            "both": {f"SRC-both-{tag}"},
            "toir_wialon_gtk": {f"SRC-all3-{tag}"},
        }
        for source, inv_numbers in expected.items():
            items, _ = await _names(source, tag)
            assert {i.inv_number for i in items} == inv_numbers, source
            assert {i.source for i in items} == {source}

        everything, _ = await _names(None, tag)
        by_inv = {i.inv_number: i.source for i in everything if i.inv_number}
        assert by_inv[f"SRC-toir-{tag}"] == "toir"
        assert by_inv[f"SRC-toir_gtk-{tag}"] == "toir_gtk"
        assert by_inv[f"SRC-both-{tag}"] == "both"
        assert by_inv[f"SRC-all3-{tag}"] == "toir_wialon_gtk"
    finally:
        await _cleanup(tag, ids, gtk_base)


async def test_gtk_only_lists_unlinked_gtk_objects_with_kind_and_id():
    tag, ids, gtk_base = await _seed()
    try:
        items, total = await _names("gtk", tag)
        names = {i.name for i in items}
        # the orphan and the one whose only link ENDED; linked ones are absent
        assert names == {f"SRC gtk orphan {tag}", f"SRC gtk ended {tag}"}
        orphan = next(i for i in items if i.name.endswith(f"orphan {tag}"))
        assert orphan.source == "gtk" and orphan.asset_id is None and orphan.unit_id is None
        assert orphan.inv_number == f"ORPH-{tag}"
        assert orphan.gtk_id == gtk_base + 3 and orphan.gtk_kind == "carriage"
        assert orphan.asset_type == "wagon"
        assert total >= 2

        none_for_diesel, count = await _names("gtk", tag, asset_type="diesel")
        assert none_for_diesel == [] and count == 0
        scoped, count = await _names("gtk", tag, master_section_id=uuid4())
        assert scoped == [] and count == 0  # a master never sees TOIR-less GTK objects
    finally:
        await _cleanup(tag, ids, gtk_base)
