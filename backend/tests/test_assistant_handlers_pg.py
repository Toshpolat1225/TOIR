"""The command centre's handlers on a real PostgreSQL: every intent answers, a master sees only his section, write intents only ask, the executors write once."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.core.database import SessionFactory
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.audit_log import AuditLog
from app.models.gtk import GtkCarriage, GtkLocomotive, GtkTrain, GtkTrainMember
from app.models.gtk_gps import GtkGpsUnit
from app.models.identity import User
from app.models.maintenance import WorkType
from app.models.organization import Employee, Section
from app.models.position_history import AssetPositionHistory
from app.models.wialon_units import WialonUnitRecord
from app.models.work_orders import WorkOrder, WorkOrderRepair
from app.schemas.assistant import AssistantContext
from app.services.assistant import handlers  # noqa: F401  (registers everything)
from app.services.assistant.catalog import INTENTS, PAGES
from app.services.assistant.registry import ACTIONS, HANDLERS
from app.services.assistant.types import AssetRef, Ctx, Slots

UTC = timezone.utc
LON = 69.57


def asset_ref(a: FixedAsset, section_name: str | None = None, gtk_id: int | None = None) -> AssetRef:
    return AssetRef(id=a.id, inv_number=a.inv_number, name=a.inv_number, asset_type=a.asset_type, section_id=a.section_id, section_name=section_name, gtk_id=gtk_id)


def all_text(result) -> str:
    parts = [result.speak or ""]
    for c in result.cards:
        parts += [c.title, c.subtitle or ""] + [f"{r.label} {r.value}" for r in c.rows] + [f"{i.label} {i.sub or ''} {i.value or ''}" for i in c.items]
    return " ".join(parts)


def test_every_catalog_intent_has_a_handler_and_every_write_has_an_executor():
    assert set(INTENTS) <= set(HANDLERS)
    assert {"wo.create", "wo.set_status", "wo.comment"} <= set(ACTIONS)
    assert not any("delete" in k for k in ACTIONS)  # nothing destroys data by voice


@pytest.mark.pg
@pytest.mark.asyncio
async def test_handlers_scope_writes_and_help():
    tag = uuid4().hex[:6]
    base = 910_000 + int(tag[:4], 16) % 80_000
    g_id, car_id, train = base, base + 1, base
    sec_a, sec_b = uuid4(), uuid4()
    admin_u, master_a_u, master_b_u = uuid4(), uuid4(), uuid4()
    loco_a, wagon_a, loco_b = uuid4(), uuid4(), uuid4()
    emp, wtype = uuid4(), uuid4()
    unit = f"AH{tag}"
    now = datetime.now(UTC).replace(microsecond=0)
    async with SessionFactory() as db:
        db.add_all([Section(id=sec_a, name=f"ZZAH-A-{tag}"), Section(id=sec_b, name=f"ZZAH-B-{tag}")])
        await db.flush()
        db.add_all([
            User(id=admin_u, email=f"zzah-admin-{tag}@example.test", full_name="ZZ Admin", hashed_password="x", role="admin"),
            User(id=master_a_u, email=f"zzah-ma-{tag}@example.test", full_name="ZZ Master A", hashed_password="x", role="master", section_id=sec_a),
            User(id=master_b_u, email=f"zzah-mb-{tag}@example.test", full_name="ZZ Master B", hashed_password="x", role="master", section_id=sec_b),
            FixedAsset(id=loco_a, inv_number=f"ZZAH-L-{tag}", asset_type="locomotive", status="operational", section_id=sec_a, mileage=Decimal("1234")),
            FixedAsset(id=wagon_a, inv_number=f"ZZAH-W-{tag}", asset_type="wagon", status="operational", section_id=sec_a),
            FixedAsset(id=loco_b, inv_number=f"ZZAH-B-{tag}", asset_type="diesel", status="operational", section_id=sec_b),
            WorkType(id=wtype, code=f"ZZAH{tag}", name=f"ZZ remont {tag}", unit_type="locomotive"),
        ])
        await db.flush()
        db.add_all([
            Employee(id=emp, tab_number=f"ZZAH-{tag}", full_name=f"ZZ Ijrochi {tag}", section_id=sec_a, is_active=True),
            WialonUnitRecord(unit_id=unit, name=unit, lat=Decimal("40.8500"), lon=Decimal(str(LON)), speed=Decimal("12"), position_at=now - timedelta(minutes=2), last_message_at=now - timedelta(minutes=2)),
            GtkGpsUnit(gtk_id=g_id, name="X", lat=Decimal("40.8500"), lon=Decimal(str(LON)), speed=Decimal("11"), position_at=now - timedelta(minutes=1)),
            GtkLocomotive(gtk_id=g_id, name=f"L{tag}", garage_number=tag, model_name="ТЭМ2", is_active=True),
            GtkCarriage(gtk_id=car_id, name=f"C{tag}", is_active=True),
            GtkTrain(gtk_id=train, number=f"T{tag}", title="t", begin_time=now - timedelta(hours=3), is_open=True),
        ])
        await db.flush()
        db.add_all([
            AssetSourceLink(asset_id=loco_a, source="wialon", external_id=unit, status="active"),
            AssetSourceLink(asset_id=loco_a, source="gtk", external_id=str(g_id), status="active"),
            AssetSourceLink(asset_id=wagon_a, source="gtk", external_id=str(car_id), status="active"),
            GtkTrainMember(train_gtk_id=train, kind="locomotive", object_gtk_id=g_id, is_main=True, ord=0, observed_from=now - timedelta(hours=3)),
            GtkTrainMember(train_gtk_id=train, kind="carriage", object_gtk_id=car_id, is_main=False, ord=1, observed_from=now - timedelta(hours=3)),
            *[AssetPositionHistory(asset_id=loco_a, at=now - timedelta(minutes=10 * (10 - i)), lat=Decimal(str(round(40.80 + 0.001 * i, 7))), lon=Decimal(str(LON)), source="wialon") for i in range(10)],
        ])
        await db.commit()
    created_orders: list = []
    try:
        async with SessionFactory() as db:
            users = {r: (await db.get(User, uid)) for r, uid in (("admin", admin_u), ("ma", master_a_u), ("mb", master_b_u))}
            mk = lambda who, locale="ru", context=None: Ctx(db=db, user=users[who], locale=locale, context=context, now=now)  # noqa: E731
            L, W, LB = asset_ref(await db.get(FixedAsset, loco_a), gtk_id=g_id), asset_ref(await db.get(FixedAsset, wagon_a), gtk_id=car_id), asset_ref(await db.get(FixedAsset, loco_b))
            run = lambda intent, ctx, **slots: HANDLERS[intent](ctx, Slots(**slots))  # noqa: E731

            # ---- reads: each answers, in both languages, and continues the conversation (entities)
            for locale in ("ru", "uz"):
                r = await run("gps.where", mk("admin", locale), asset=L)
                assert r.status == "ok" and r.cards and r.speak and "40.8" in all_text(r) and r.entities[0].id == str(loco_a)
            r = await run("gps.status", mk("admin"), asset=L)
            assert r.status == "ok" and "Wialon" in all_text(r) and "GTK" in all_text(r)
            r = await run("gps.km", mk("admin"), asset=L, period="week")
            assert r.status == "ok" and r.cards[0].kind == "metric"
            r = await run("gps.why_diff", mk("admin"), asset=L)
            assert r.status == "ok" and r.speak
            r = await run("gps.why_diff", mk("admin"))  # no asset: the overall causes
            assert r.status == "ok" and r.cards
            r = await run("gps.dead_trackers", mk("admin"))
            assert r.status == "ok" and r.speak
            r = await run("gps.summary", mk("admin"))
            assert r.status == "ok" and "GPS" in r.cards[0].title
            r = await run("map.show", mk("admin"), asset=L)
            assert r.navigate == f"/dashboard/gps/{loco_a}"
            r = await run("wagon.loco", mk("admin"), asset=W)
            assert r.status == "ok" and L.inv_number in all_text(r)
            r = await run("gps.where", mk("admin"), asset=W)
            assert r.status == "ok" and "T" + tag in all_text(r)
            r = await run("gps.km", mk("admin"), asset=W, period="today")
            assert r.status == "ok"
            r = await run("train.info", mk("admin"), train_no=f"T{tag}")
            assert r.status == "ok" and r.entities[0].kind == "train" and "1" in all_text(r)
            r = await run("find.asset", mk("admin"), asset=L)
            assert r.status == "ok" and "1 234" in all_text(r) or "1234" in all_text(r)
            r = await run("asset.info", mk("admin"), asset=L)
            assert r.status == "ok" and len(r.cards[0].rows) >= 5
            r = await run("mileage.asset", mk("admin"), asset=L)
            assert r.status == "ok" and "1 234" in all_text(r) or "1234" in all_text(r)
            for intent in ("to.overdue", "to.schedule", "wo.count", "wo.list", "scales.today", "sys.sync_status"):
                r = await run(intent, mk("admin"))
                assert r.status == "ok" and r.speak and r.cards, intent
            r = await run("to.next", mk("admin"), asset=L)
            assert r.status == "ok" and r.speak
            r = await run("scales.wagon", mk("admin"), asset=W)
            assert r.status in ("ok", "error")  # a wagon with no weighings answers (404 -> not found text), never raises
            r = await run("nav.open", mk("admin"), page="map")
            assert r.navigate == PAGES["map"][0]
            r = await run("nav.open", mk("ma"), page="users")  # the page's own permission (users.manage_users) is not a master's
            assert r.status == "denied" and r.navigate is None
            r = await run("nav.open", mk("admin"))
            assert r.status == "needs_clarification"
            r = await run("sys.help", mk("ma", "uz"))
            titles = " ".join(c.title for c in r.cards)
            assert r.cards and "Admin" not in titles and "audit" not in all_text(r).lower()  # a master is not offered the admin commands
            r = await run("admin.audit_recent", mk("admin"))
            assert r.status == "ok"
            r = await run("admin.audit_recent", mk("ma"))
            assert r.status == "denied"

            # ---- context: "bu lokomotiv"
            ctx_page = AssistantContext(asset_id=loco_a)
            r = await run("gps.where", mk("admin", context=ctx_page))
            assert r.status == "ok" and r.entities[0].id == str(loco_a)
            r = await run("gps.where", mk("admin"))  # nothing to refer to: it asks
            assert r.status == "needs_clarification"
            r = await run("gps.where", mk("admin"), assets=[L, LB])  # ambiguous: a list of candidates
            assert r.status == "needs_clarification" and len(r.cards[0].items) == 2 and r.cards[0].items[0].entity is not None

            # ---- master scoping: another section's asset is simply not found, in every asset handler
            for intent in ("gps.where", "gps.status", "gps.km", "mileage.asset", "find.asset", "asset.info", "to.next", "map.show"):
                r = await run(intent, mk("ma"), asset=LB)
                assert r.status == "error" and not r.entities and "ZZAH-B" not in all_text(r), intent
            r = await run("gps.where", mk("mb"), asset=L)
            assert r.status == "error"
            r = await run("train.info", mk("mb"), train_no=f"T{tag}")  # a master of another section sees the train, but not the locomotive's identity
            assert f"ZZAH-L-{tag}" not in all_text(r)
            r = await run("train.info", mk("ma"), train_no=f"T{tag}")
            assert f"ZZAH-L-{tag}" in all_text(r)

            # ---- write intents only ask (nothing is written), with a clear summary
            before = (await db.execute(select(func.count()).select_from(WorkOrder).where(WorkOrder.fixed_asset_id == loco_a))).scalar_one()
            r = await run("wo.create", mk("admin"), asset=L, text="almashtirish tormoz")
            assert r.pending is not None and r.pending.kind == "wo.create" and r.cards[0].kind == "confirm"
            assert f"ZZ Ijrochi {tag}" in r.pending.summary and r.pending.payload["work_type_id"] and "tormoz" in r.pending.summary  # the user sees who and what before confirming
            assert (await db.execute(select(func.count()).select_from(WorkOrder).where(WorkOrder.fixed_asset_id == loco_a))).scalar_one() == before
            r = await run("wo.create", mk("mb"), asset=L, text="x")  # a master of another section: not found, no pending
            assert r.pending is None and r.status == "error"
            r = await run("wo.create", mk("admin"), asset=LB, text="x")  # a section without an active employee asks instead of guessing
            assert r.pending is None and r.status == "needs_clarification"
            payload = (await run("wo.create", mk("ma"), asset=L, text="almashtirish tormoz")).pending.payload
            assert payload["executor_id"] == str(emp)

            # ---- the executor writes once, through the service (audited); the second master cannot replay it
            denied_r = await ACTIONS["wo.create"](mk("mb"), payload)
            assert denied_r.status in ("denied", "error")
            assert (await db.execute(select(func.count()).select_from(WorkOrder).where(WorkOrder.fixed_asset_id == loco_a))).scalar_one() == before
            created = await ACTIONS["wo.create"](mk("ma"), payload)
            assert created.status == "ok" and created.entities[0].kind == "work_order"
            number = created.entities[0].label
            order_id = created.entities[0].id
            created_orders.append(order_id)
            assert (await db.execute(select(func.count()).select_from(WorkOrder).where(WorkOrder.fixed_asset_id == loco_a))).scalar_one() == before + 1
            audited = (await db.execute(select(func.count()).select_from(AuditLog).where((AuditLog.object_id == order_id) | (AuditLog.object_label == number)))).scalar_one()
            assert audited >= 1

            # ---- find the order by its number, change its status (pending -> in_progress -> completed), comment
            digits = "".join(ch for ch in number if ch.isdigit())
            r = await run("wo.list", mk("ma"))
            assert number in all_text(r)
            r = await run("wo.by_asset", mk("ma"), asset=L)
            assert number in all_text(r) and r.entities[0].id == str(loco_a)
            r = await run("wo.by_asset", mk("mb"), asset=L)  # another section's asset: not found
            assert r.status == "error"
            r = await run("wo.by_asset", mk("admin"), asset=LB)
            assert r.status == "ok" and number not in all_text(r)
            r = await run("wo.count", mk("ma"))
            assert r.status == "ok"
            r = await run("wo.set_status", mk("ma"), work_order=digits[-6:], status="in_progress")
            assert r.pending is not None and r.pending.payload["status"] == "in_progress"
            r_bad = await run("wo.set_status", mk("ma"), work_order=digits[-6:], status="completed")  # pending -> completed is not allowed
            assert r_bad.pending is None and r_bad.status == "error"
            r_other = await run("wo.set_status", mk("mb"), work_order=digits[-6:], status="in_progress")  # another section's order: not found
            assert r_other.pending is None and r_other.status == "error"
            assert (await db.get(WorkOrder, __import__("uuid").UUID(order_id))).status == "pending"  # still untouched
            done = await ACTIONS["wo.set_status"](mk("ma"), r.pending.payload)
            assert done.status == "ok"
            async with SessionFactory() as chk:  # a fresh session sees only what was committed
                assert (await chk.get(WorkOrder, __import__("uuid").UUID(order_id))).status == "in_progress"
            r = await run("wo.comment", mk("ma"), work_order=digits[-6:], text="ehtiyot qism kutilmoqda")
            assert r.pending is not None and r.pending.kind == "wo.comment"
            c = await ACTIONS["wo.comment"](mk("ma"), r.pending.payload)
            assert c.status == "ok"
            async with SessionFactory() as chk:
                order = await chk.get(WorkOrder, __import__("uuid").UUID(order_id))
                assert order.note and "ehtiyot qism kutilmoqda" in order.note
            r = await run("wo.comment", mk("ma"), work_order=digits[-6:])  # no text: it asks
            assert r.status == "needs_clarification" and r.pending is None
            r = await run("wo.set_status", mk("ma"), work_order="12")  # too short a number
            assert r.status == "needs_clarification"
            r = await run("wo.set_status", mk("ma"), work_order=digits[-6:])  # no status
            assert r.status == "needs_clarification"
            # an operator without the update permission is refused by the handler itself
            users["op"] = User(id=uuid4(), email=f"zzah-op-{tag}@example.test", full_name="ZZ Op", hashed_password="x", role="management")
            r = await HANDLERS["admin.audit_recent"](mk("op"), Slots())
            assert r.status == "denied"
    finally:
        async with SessionFactory() as db:
            ids = [__import__("uuid").UUID(x) for x in created_orders]
            if ids:
                await db.execute(delete(WorkOrderRepair).where(WorkOrderRepair.work_order_id.in_(ids)))
                await db.execute(delete(WorkOrder).where(WorkOrder.id.in_(ids)))
            await db.execute(delete(AuditLog).where(AuditLog.object_id.in_([str(i) for i in ids] + [str(loco_a)])))
            await db.execute(delete(AssetPositionHistory).where(AssetPositionHistory.asset_id == loco_a))
            await db.execute(delete(GtkTrainMember).where(GtkTrainMember.train_gtk_id == train))
            await db.execute(delete(GtkTrain).where(GtkTrain.gtk_id == train))
            await db.execute(delete(AssetSourceLink).where(AssetSourceLink.asset_id.in_([loco_a, wagon_a, loco_b])))
            await db.execute(delete(GtkCarriage).where(GtkCarriage.gtk_id == car_id))
            await db.execute(delete(GtkLocomotive).where(GtkLocomotive.gtk_id == g_id))
            await db.execute(delete(GtkGpsUnit).where(GtkGpsUnit.gtk_id == g_id))
            await db.execute(delete(WialonUnitRecord).where(WialonUnitRecord.unit_id == unit))
            await db.execute(delete(Employee).where(Employee.id == emp))
            await db.execute(delete(WorkType).where(WorkType.id == wtype))
            await db.execute(delete(FixedAsset).where(FixedAsset.id.in_([loco_a, wagon_a, loco_b])))
            await db.execute(delete(User).where(User.id.in_([admin_u, master_a_u, master_b_u])))
            await db.execute(delete(Section).where(Section.id.in_([sec_a, sec_b])))
            await db.commit()
