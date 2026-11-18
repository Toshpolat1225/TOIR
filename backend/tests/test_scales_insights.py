"""The command-center payloads: overview, train / wagon / locomotive cards (joins over scales, GTK, assets, sections, maintenance)."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.core.database import SessionFactory
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.gtk import GtkCarriage, GtkLocomotive, GtkTrain, GtkTrainMember
from app.models.organization import Section
from app.models.scales import ScalePost, ScaleTrain
from app.schemas import scales as schemas
from app.services import scales as service
from app.services import scales_insights as insights

UTC = timezone.utc


@pytest.mark.pg
@pytest.mark.asyncio
async def test_cards_and_overview_join_scales_gtk_assets_and_maintenance():
    tag = uuid4().hex[:6]
    code, garage = f"I{tag}", f"K{tag}".upper()
    base = 700_000 + int(tag[:4], 16) % 90_000
    loco_gtk, train_gtk, cars = base, base, [base + 1, base + 2, base + 3]
    section, loco, w1, w2 = uuid4(), uuid4(), uuid4(), uuid4()
    # the page counts «today» in the LOCAL day (UTC+5): never start before local midnight, or the test depends on the hour it runs at
    local_midnight = (datetime.now(UTC) + timedelta(hours=5)).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=5)
    start = max(datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=40), local_midnight + timedelta(minutes=5))
    yesterday = date.today() - timedelta(days=1)
    async with SessionFactory() as db:
        db.add(Section(id=section, name=f"INS-{tag}"))
        await db.flush()
        db.add_all([
            FixedAsset(id=loco, inv_number=f"IN-L-{tag}", asset_type="locomotive", status="operational", section_id=section, last_maint_date=yesterday),
            FixedAsset(id=w1, inv_number=f"IN-W1-{tag}", asset_type="wagon", status="operational", section_id=section),
            FixedAsset(id=w2, inv_number=f"IN-W2-{tag}", asset_type="wagon", status="operational", section_id=section, last_maint_date=yesterday),
        ])
        await db.flush()
        db.add_all([GtkLocomotive(gtk_id=loco_gtk, name=f"TA {garage}", garage_number=garage, is_active=True)]
                   + [GtkCarriage(gtk_id=c, name=f"IC{c}", is_active=True) for c in cars]
                   + [GtkTrain(gtk_id=train_gtk, number=garage, title="ins", begin_time=start - timedelta(hours=1), is_open=True)])
        await db.flush()
        db.add_all([
            GtkTrainMember(train_gtk_id=train_gtk, kind="locomotive", object_gtk_id=loco_gtk, is_main=True, ord=0, observed_from=start - timedelta(hours=1)),
            *[GtkTrainMember(train_gtk_id=train_gtk, kind="carriage", object_gtk_id=c, is_main=False, ord=i + 1, observed_from=start - timedelta(hours=1)) for i, c in enumerate(cars)],
            AssetSourceLink(asset_id=loco, source="gtk", external_id=str(loco_gtk), status="active"),
            AssetSourceLink(asset_id=w1, source="gtk", external_id=str(cars[0]), status="active"),
            AssetSourceLink(asset_id=w2, source="gtk", external_id=str(cars[1]), status="active"),  # the third car stays unlinked
        ])
        await db.commit()

    def train(src, when, weight):
        return schemas.ScaleTrainIn(src_id=src, loco_number=garage, declared_wagons=5, reported_weight_t=weight, started_at=when, finished_at=when + timedelta(minutes=8), cargo_code=33, excavator=46)

    def unit(src, train_src, pos, tare, net, when):
        return schemas.ScaleWeighingIn(src_id=src, train_src_id=train_src, position=pos, gross_t=tare + net, tare_t=tare, net_t=net, capacity_t=105, speed_kmh=4.2, axles=4, weighed_at=when)

    second = start + timedelta(minutes=20)
    payload = schemas.ScalesIngestIn(
        post=code, tare_default_t=49, capacity_norm_t=105, cargo=[schemas.ScaleCargoIn(code=33, name="Кальмакыр")],
        trains=[train(1, start, 490.0), train(2, second, 520.0)],
        weighings=[unit(11, 1, 1, 126, 44, start), unit(12, 1, 2, 126, 44, start), unit(13, 1, 3, 49, 100, start), unit(14, 1, 4, 49, 110, start), unit(15, 1, 5, 49, 90, start),
                   unit(21, 2, 1, 126, 44, second), unit(22, 2, 2, 126, 44, second), unit(23, 2, 3, 49, 100, second), unit(24, 2, 4, 49, 100, second), unit(25, 2, 5, 49, 100, second)],
    )
    try:
        async with SessionFactory() as db:
            await service.ingest(db, payload)
        async with SessionFactory() as db:
            ids = {t.src_id: t.id for t in (await db.execute(select(ScaleTrain).join(ScalePost).where(ScalePost.code == code))).scalars().all()}

            ov = await insights.overview(db, 7)
            assert ov.kpi.trains >= 2 and ov.kpi.tonnes >= Decimal("600") and ov.days == 7 and (ov.date_to - ov.date_from).days == 6
            mine = next(l for l in ov.top_locomotives if l.asset_id == loco)
            assert (mine.trains, mine.tonnes, mine.inv_number) == (2, Decimal("600.00"), f"IN-L-{tag}")
            assert {ids[1], ids[2]} <= {x.id for x in ov.today} and ov.quality.by_status.get("ok", 0) >= 2
            assert any(p.post_code == code and p.trains == 2 for p in ov.daily) and any(h.post_code == code for h in ov.hourly)
            assert any(c.label == "Кальмакыр" for c in ov.by_cargo) and any(e.key == "46" for e in ov.by_excavator)

            card = await insights.train_card(db, ids[1])
            assert (card.post_code, card.match_status, card.dump_count, card.traction_count, card.net_total_t) == (code, "ok", 3, 2, Decimal("300.00"))
            assert card.cargo_name == "Кальмакыр" and card.loco and card.loco.inv_number == f"IN-L-{tag}" and card.loco.section_name == f"INS-{tag}"
            assert card.gtk_train and card.gtk_train.number == garage and card.gtk_loco and card.gtk_loco.garage_number == garage
            assert card.offset_t == Decimal("190.00") and card.avg_car_t == Decimal("100.00")  # «Вес» 490 - cargo 300
            assert [(u.position, u.kind) for u in card.units] == [(1, "traction"), (2, "traction"), (3, "dump"), (4, "dump"), (5, "dump")]
            assert [(u.inv_number, u.net_t) for u in card.units if u.kind == "dump"] == [(f"IN-W1-{tag}", Decimal("100.00")), (f"IN-W2-{tag}", Decimal("110.00")), (None, Decimal("90.00"))]
            assert [(c.ord, c.unit_position, c.net_t) for c in card.carriages] == [(1, 3, Decimal("100.00")), (2, 4, Decimal("110.00")), (3, 5, Decimal("90.00"))]
            assert card.prev_id is None and card.next_id == ids[2] and (await insights.train_card(db, ids[2])).prev_id == ids[1]
            with pytest.raises(HTTPException) as missing:
                await insights.train_card(db, uuid4())
            assert missing.value.status_code == 404

            wagon = await insights.wagon_card(db, asset_id=w2, carriage_gtk_id=None, days=7)
            assert wagon.asset and wagon.asset.inv_number == f"IN-W2-{tag}" and wagon.asset.section_name == f"INS-{tag}" and wagon.gtk and wagon.gtk.name == f"IC{cars[1]}"
            assert (wagon.period.trips, wagon.period.tonnes, wagon.period.own_trips, wagon.period.overload_trips) == (2, Decimal("210.00"), 2, 1)  # 110 t > 105 t capacity once
            assert [r.basis for r in wagon.recent] == ["own", "own"] and wagon.by_loco[0].label == garage and wagon.by_cargo[0].label == "Кальмакыр"
            assert wagon.maintenance and wagon.maintenance.last_service_at == yesterday and wagon.maintenance.trips_since == 2 and wagon.maintenance.tonnes_since == Decimal("210.00")
            assert wagon.maintenance.last_service_source == "дата в карточке ОС"
            unlinked = await insights.wagon_card(db, asset_id=None, carriage_gtk_id=cars[2], days=7)
            assert unlinked.asset is None and unlinked.maintenance is None and unlinked.gtk and unlinked.period.trips == 2 and unlinked.period.tonnes == Decimal("190.00")

            loco_view = await insights.loco_card(db, loco, 7)
            assert (loco_view.period.trips, loco_view.period.tonnes, loco_view.avg_cars) == (2, Decimal("600.00"), Decimal("3.00"))
            assert loco_view.numbers_used == [garage] and loco_view.gtk and loco_view.gtk.garage_number == garage and loco_view.wialon is None
            assert loco_view.top_wagons[0].label == f"IN-W2-{tag}" and loco_view.top_wagons[0].tonnes == Decimal("210.00") and loco_view.top_wagons[0].trips == 2
            assert loco_view.maintenance.trips_since == 2 and [t.cars for t in loco_view.recent] == [3, 3]
            for call in (insights.wagon_card(db, asset_id=loco, carriage_gtk_id=None, days=7), insights.loco_card(db, w1, 7)):
                with pytest.raises(HTTPException) as wrong:
                    await call
                assert wrong.value.status_code == 422
            with pytest.raises(HTTPException) as nothing:
                await insights.wagon_card(db, asset_id=None, carriage_gtk_id=None, days=7)
            assert nothing.value.status_code == 422
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(ScalePost).where(ScalePost.code == code))
            await db.execute(delete(AssetSourceLink).where(AssetSourceLink.asset_id.in_([loco, w1, w2])))
            await db.execute(delete(GtkTrainMember).where(GtkTrainMember.train_gtk_id == train_gtk))
            await db.execute(delete(GtkTrain).where(GtkTrain.gtk_id == train_gtk))
            await db.execute(delete(GtkCarriage).where(GtkCarriage.gtk_id.in_(cars)))
            await db.execute(delete(GtkLocomotive).where(GtkLocomotive.gtk_id == loco_gtk))
            await db.execute(delete(FixedAsset).where(FixedAsset.id.in_([loco, w1, w2])))
            await db.execute(delete(Section).where(Section.id == section))
            await db.commit()
