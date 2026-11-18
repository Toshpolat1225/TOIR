"""Day assessments, filters/facets/export, tracker health and wagon segments on a real PostgreSQL."""
import io
import zipfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.core.database import SessionFactory
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.gtk import GtkCarriage, GtkLocomotive, GtkTrain, GtkTrainMember
from app.models.gtk_gps import GpsDayAssessment, GpsWagonSegment, GtkGpsDay, GtkGpsUnit
from app.models.organization import Section
from app.models.position_history import AssetPositionHistory
from app.models.mileage import WialonOdometerReading
from app.models.wialon_units import WialonUnitRecord
from app.services import gps_assessment as assess
from app.services import gps_overview as overview
from app.services import gps_wagons as wagons
from app.services import wagon_gps

UTC = timezone.utc
LON = 69.57


def lat_of(i):
    return 40.80 + 0.001 * i


@pytest.mark.pg
@pytest.mark.asyncio
async def test_assessment_filters_export_health_and_wagons():
    tag = uuid4().hex[:6]
    base = 800_000 + int(tag[:4], 16) % 90_000
    g_id, loco_gtk, car_id = base, base + 1, base + 2
    sec_a, sec_b = uuid4(), uuid4()
    loco, wagon, wagon2, other = uuid4(), uuid4(), uuid4(), uuid4()
    unit = f"GA{tag}"
    train = base
    now = datetime.now(UTC).replace(microsecond=0)
    local_today = assess.local_today(now, 5)
    yesterday = local_today - timedelta(days=1)
    y0, _ = assess.local_day_bounds(yesterday, 5)
    # yesterday (local): Wialon every 10 minutes all day, GTK only the first 4 hours
    w_pts = [(y0 + timedelta(minutes=10 * i + 1), lat_of(i)) for i in range(143)]
    g_pts = w_pts[:24]
    # the last 3 hours before now: both trackers, for the wagon segment
    recent = [(now - timedelta(minutes=10 * (18 - i)), lat_of(100 + i)) for i in range(18)]
    async with SessionFactory() as db:
        db.add_all([Section(id=sec_a, name=f"WA-{tag}"), Section(id=sec_b, name=f"WB-{tag}")])
        await db.flush()
        db.add_all([
            FixedAsset(id=loco, inv_number=f"WL-{tag}", asset_type="locomotive", status="operational", section_id=sec_a),
            FixedAsset(id=other, inv_number=f"WO-{tag}", asset_type="diesel", status="operational", section_id=sec_b),
            FixedAsset(id=wagon, inv_number=f"WW-{tag}", asset_type="wagon", status="operational", section_id=sec_a),
            FixedAsset(id=wagon2, inv_number=f"WX-{tag}", asset_type="wagon", status="operational", section_id=sec_b),
        ])
        await db.flush()
        db.add_all([
            WialonUnitRecord(unit_id=unit, name=unit, lat=Decimal(str(lat_of(117))), lon=Decimal(str(LON)), speed=Decimal("0"), position_at=now - timedelta(minutes=2), last_message_at=now - timedelta(minutes=2)),
            GtkGpsUnit(gtk_id=g_id, name="X", lat=Decimal(str(lat_of(117))), lon=Decimal(str(LON)), speed=Decimal("0"), position_at=now - timedelta(minutes=1)),
            GtkLocomotive(gtk_id=loco_gtk, name=f"L{tag}", garage_number=tag, model_name="ТЭМ2", is_active=True),
            GtkCarriage(gtk_id=car_id, name=f"C{tag}", is_active=True),
            GtkTrain(gtk_id=train, number=f"N{tag}", title="t", begin_time=now - timedelta(hours=3), is_open=True),
        ])
        await db.flush()
        db.add_all([
            AssetSourceLink(asset_id=loco, source="wialon", external_id=unit, status="active"),
            AssetSourceLink(asset_id=loco, source="gtk", external_id=str(g_id), status="active"),
            AssetSourceLink(asset_id=wagon, source="gtk", external_id=str(car_id), status="active"),
            GtkGpsDay(gtk_id=g_id, day=yesterday, distance_m=2600, points=300, is_final=True, events={"noreasonidle": 2}),
        ])
        db.add_all([AssetPositionHistory(asset_id=loco, at=at, lat=Decimal(str(round(lat, 7))), lon=Decimal(str(LON)), source="wialon") for at, lat in w_pts + recent])
        db.add_all([AssetPositionHistory(asset_id=loco, at=at, lat=Decimal(str(round(lat, 7))), lon=Decimal(str(LON)), source="gtk_gps") for at, lat in g_pts + recent])
        await db.commit()
        # the Wialon odometer ticked along the same path: ~111 m per 10 minutes, a reading every 20 minutes, 2% more than the thinned track
        db.add_all([
            WialonOdometerReading(
                asset_id=loco, source_unit_id=unit, odometer_km=Decimal(str(round(5000 + 1.02 * 0.1112 * 2 * k, 2))), reading_at=y0 + timedelta(minutes=20 * k + 1),
                observed_at=y0 + timedelta(minutes=20 * k + 1), accepted=True, calculation_eligible=True, classification="CONFIRMED",
                payload_hash=f"odo-{tag}-{k}", payload={"t": k},
            )
            for k in range(-14, 80)
        ])
        await db.commit()
    # the GTK id used by the segment job is the link's external id, the train page uses the same id for the locomotive
    try:
        async with SessionFactory() as db:
            # ---- the day assessment: GTK silent for 20 of the 24 hours
            [a] = await assess.assess_days(db, {loco: g_id}, [yesterday], now)
            assert a.cause == "gtk_gaps" and a.verdict == "gtk_gap" and a.gtk_gap_h > 15 and a.wialon_gap_h < 1
            assert a.fused_m >= a.wialon_m * 0.97 and a.confidence is not None and a.is_final
            assert "GTK" in a.explanation
            # the odometer agrees with the Wialon track while GTK is mostly missing: 0.97 (both trackers reported, one corroborated by a third source)
            assert a.odo_m is not None and a.odo_agrees is True and a.confidence == 0.97 and "Одометр" in a.explanation
            assert await assess.persist(db, [a], now) == 1
            await db.commit()
            got = await assess.ensure_days(db, {loco: g_id}, [yesterday, local_today], now)
            assert got[(loco, yesterday)].persisted and got[(loco, yesterday)].cause == "gtk_gaps" and not got[(loco, local_today)].persisted  # today is always live

            # ---- overview: facets, filters, sort, export
            admin = SimpleNamespace(role="admin", section_id=None)
            f = overview.Filters(days=2, q=f"-{tag}")
            page = await overview.get_overview(db, admin, f, with_facets=True)
            row = next(r for r in page.items if r.inv_number == f"WL-{tag}")
            assert row.days[1].cause == "gtk_gaps" and row.top_cause == "gtk_gaps" and row.week_fused_m >= row.week_wialon_m * 0.97
            assert row.health is not None and row.health.health_class in {"intermittent", "ok"} and row.week_confidence is not None
            assert page.facets["cause"].get("gtk_gaps", 0) >= 1 and page.facets["link"].get("both", 0) >= 1 and page.summary.cause_counts.get("gtk_gaps", 0) >= 1
            by = lambda **k: [r.inv_number for r in (overview.sort_rows([x for x in page_rows if overview.matches(x, overview.Filters(days=2, q=f"-{tag}", **k))], "inv_number", "asc"))]  # noqa: E731
            page_rows, _, _ = await overview.filtered_rows(db, admin, overview.Filters(days=2))
            assert by(cause=["gtk_gaps"]) == [f"WL-{tag}"] and f"WL-{tag}" not in by(cause=["ok"])
            assert by(link="both") == [f"WL-{tag}"] and by(link="none") == [f"WO-{tag}"]
            assert f"WL-{tag}" in by(bbox=(40.0, 69.0, 41.5, 70.0))
            assert by(bbox=(10.0, 10.0, 11.0, 11.0)) == []
            assert by(health=["dead"]) == []
            narrowed = await overview.get_overview(db, admin, overview.Filters(days=2, q=f"-{tag}", cause=["gtk_gaps"]), with_facets=True)
            assert [r.inv_number for r in narrowed.items] == [f"WL-{tag}"] and narrowed.summary.assets >= 2  # the summary stays whole-scope
            assert narrowed.facets["cause"].get("gtk_gaps", 0) >= 1  # a facet ignores its own filter
            with pytest.raises(HTTPException) as bad_sort:
                overview.sort_rows(page_rows, "nonsense", "asc")
            assert bad_sort.value.status_code == 422
            shown = [r for r in page_rows if f"-{tag}" in r.inv_number]
            csv_bytes = overview.to_csv(shown)
            assert csv_bytes.startswith("﻿".encode()) and f"WL-{tag}".encode() in csv_bytes
            with zipfile.ZipFile(io.BytesIO(overview.to_xlsx(shown))) as z:
                assert f"WL-{tag}" in z.read("xl/worksheets/sheet1.xml").decode()
            health = await overview.get_health(db, admin, q=f"-{tag}")
            assert any(h.inv_number == f"WL-{tag}" for h in health.items) and health.counts

            # ---- wagons: membership -> segments -> list/detail
            db.add_all([
                GtkTrainMember(train_gtk_id=train, kind="locomotive", object_gtk_id=g_id, is_main=True, ord=0, observed_from=now - timedelta(hours=3)),
                GtkTrainMember(train_gtk_id=train, kind="carriage", object_gtk_id=car_id, is_main=False, ord=1, observed_from=now - timedelta(hours=3)),
            ])
            await db.commit()
            n = await wagon_gps.compute_segments(db, now, back_days=2)
            assert n >= 1
            again = await wagon_gps.compute_segments(db, now, back_days=2)  # idempotent: the same keys, no duplicates
            segs = (await db.execute(select(GpsWagonSegment).where(GpsWagonSegment.carriage_gtk_id == car_id))).scalars().all()
            assert len(segs) == again and all(s.loco_asset_id == loco and s.wagon_asset_id == wagon for s in segs)
            assert any(s.selected_km is not None and float(s.selected_km) > 1.0 for s in segs) and all(s.basis in {"fused_track", "track", "single_source", "conflict", "held"} for s in segs)
            page = await wagons.list_wagons(db, admin, q=f"-{tag}", now=now)
            w = next(r for r in page.items if r.carriage_gtk_id == car_id)
            assert w.in_train and w.train_gtk_id == train and w.loco_inv_number == f"WL-{tag}" and w.position is not None and w.km_period > 1.0
            assert w.confidence in {"high", "medium"} and page.summary.history_from is not None
            detail = await wagons.wagon_detail(db, admin, str(wagon), now=now)
            assert detail.segments and detail.segments[0].loco_inv_number == f"WL-{tag}" and "локомотив" in (detail.explanation or "")
            assert (await wagons.wagon_detail(db, admin, f"gtk-{car_id}", now=now)).row.carriage_gtk_id == car_id
            # a second open membership flags the wagon
            db.add(GtkTrainMember(train_gtk_id=train + 5, kind="carriage", object_gtk_id=car_id, is_main=False, ord=1, observed_from=now - timedelta(hours=1)))
            await db.commit()
            flagged = next(r for r in (await wagons.list_wagons(db, admin, q=f"-{tag}", now=now)).items if r.carriage_gtk_id == car_id)
            assert "two_trains" in flagged.flags
            # masters: own section only, strangers 404, the section query is ignored
            master_a, master_b = SimpleNamespace(role="master", section_id=sec_a), SimpleNamespace(role="master", section_id=sec_b)
            assert {r.carriage_gtk_id for r in (await wagons.list_wagons(db, master_a, q=f"-{tag}", now=now)).items} == {car_id}
            assert (await wagons.list_wagons(db, master_b, q=f"-{tag}", now=now)).items == []
            with pytest.raises(HTTPException) as stranger:
                await wagons.wagon_detail(db, master_b, str(wagon), now=now)
            assert stranger.value.status_code == 404
            with pytest.raises(HTTPException) as gtk_only:
                await wagons.wagon_detail(db, master_a, f"gtk-{car_id}", now=now)
            assert gtk_only.value.status_code == 404
            master_page = await overview.get_overview(db, SimpleNamespace(role="master", section_id=sec_a), overview.Filters(days=2, q=f"-{tag}", section_id=sec_b), with_facets=True)
            assert {r.inv_number for r in master_page.items} == {f"WL-{tag}"}
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(GpsWagonSegment).where(GpsWagonSegment.carriage_gtk_id == car_id))
            await db.execute(delete(GtkTrainMember).where(GtkTrainMember.train_gtk_id.in_([train, train + 5])))
            await db.execute(delete(GtkTrain).where(GtkTrain.gtk_id == train))
            await db.execute(delete(WialonOdometerReading).where(WialonOdometerReading.asset_id == loco))
            await db.execute(delete(GpsDayAssessment).where(GpsDayAssessment.asset_id.in_([loco, other])))
            await db.execute(delete(GtkGpsDay).where(GtkGpsDay.gtk_id == g_id))
            await db.execute(delete(GtkGpsUnit).where(GtkGpsUnit.gtk_id == g_id))
            await db.execute(delete(AssetPositionHistory).where(AssetPositionHistory.asset_id.in_([loco, other])))
            await db.execute(delete(AssetSourceLink).where(AssetSourceLink.asset_id.in_([loco, wagon, wagon2, other])))
            await db.execute(delete(GtkCarriage).where(GtkCarriage.gtk_id == car_id))
            await db.execute(delete(GtkLocomotive).where(GtkLocomotive.gtk_id == loco_gtk))
            await db.execute(delete(WialonUnitRecord).where(WialonUnitRecord.unit_id == unit))
            await db.execute(delete(FixedAsset).where(FixedAsset.id.in_([loco, wagon, wagon2, other])))
            await db.execute(delete(Section).where(Section.id.in_([sec_a, sec_b])))
            await db.commit()
