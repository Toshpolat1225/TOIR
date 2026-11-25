"""Spare-part analytics + 1C import on PostgreSQL: forecast, demand, consumption, stock risk, master scoping, import dry-run/apply (needs the pg test database)."""
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import delete, select, text

from app.core.database import SessionFactory
from app.core.timeutil import today_local
from app.models.assets import FixedAsset
from app.models.identity import User
from app.models.inventory import Nomenclature, NomenclatureNorm
from app.models.maintenance import MaintenanceInterval, MaintenancePlan, WorkType
from app.models.organization import Department, Section
from app.models.stock import PurchaseOrder, StockBalance, SupplierTerm
from app.models.tmc import TmcDocument, TmcDocumentItem
from app.schemas.stock import PurchaseOrderCreate, PurchaseOrderWrite, SupplierTermWrite
from app.services import parts_analytics as svc
from app.services import stock as stock_svc
from app.services import stock_import as si
from user_factory import ad_user

pytestmark = [pytest.mark.pg, pytest.mark.asyncio]
TODAY = today_local()


class World:
    def __init__(self):
        self.tag = uuid4().hex[:8]
        self.ids = {k: uuid4() for k in ("secA", "secB", "secC", "wt", "iv", "n1", "n2", "d_pol", "d_two", "a1", "a2", "uAdmin", "uA", "uB", "uC")}
        self.made_dept = False

    async def seed(self):
        i, tag = self.ids, self.tag
        async with SessionFactory() as db:
            dept = (await db.execute(select(Department).where(Department.name == "Участок ПТОЛ"))).scalar_one_or_none()
            if dept is None:
                db.add(Department(id=i["d_pol"], name="Участок ПТОЛ"))
                self.made_dept = True
            else:
                i["d_pol"] = dept.id
            db.add(Department(id=i["d_two"], name=f"Dept2-{tag}"))
            for k in ("secA", "secB", "secC"):
                db.add(Section(id=i[k], name=f"S{k}-{tag}"))
            db.add(WorkType(id=i["wt"], code=f"W-{tag}", name="wt", unit_type="locomotive"))
            await db.flush()
            db.add(MaintenanceInterval(id=i["iv"], code=f"I-{tag}", name="iv", interval_days=40, rank=1, work_type_id=i["wt"]))
            db.add(Nomenclature(id=i["n1"], department_id=i["d_pol"], name=f"Деталь-{tag}", code=f"C-{tag}", unit="шт"))
            db.add(Nomenclature(id=i["n2"], department_id=i["d_pol"], name=f"Дубль-{tag}", unit="шт"))
            db.add(Nomenclature(department_id=i["d_two"], name=f"Дубль-{tag}", unit="шт"))
            await db.flush()
            db.add(NomenclatureNorm(nomenclature_id=i["n1"], department_id=i["d_pol"], work_type_id=i["wt"], standard_quantity=Decimal("2"), avg_price=Decimal("100")))
            db.add(FixedAsset(id=i["a1"], inv_number=f"PA1-{tag}", asset_type="diesel", section_id=i["secA"], year_built=TODAY.year - 3, mileage=Decimal(0)))
            db.add(FixedAsset(id=i["a2"], inv_number=f"PA2-{tag}", asset_type="diesel", section_id=i["secB"], year_built=1990, mileage=Decimal(0)))
            await db.flush()
            db.add(MaintenancePlan(asset_id=i["a1"], interval_id=i["iv"], status="scheduled", scheduled_date=TODAY + timedelta(days=10)))
            db.add(MaintenancePlan(asset_id=i["a2"], interval_id=i["iv"], status="scheduled", scheduled_date=TODAY + timedelta(days=20)))
            db.add(MaintenancePlan(asset_id=i["a2"], interval_id=i["iv"], status="completed", trigger_mileage=Decimal(5), scheduled_date=TODAY + timedelta(days=21)))  # not open: ignored
            for sec, qty in (("secA", 5), ("secB", 3)):
                doc = TmcDocument(doc_no=f"PD-{sec}-{tag}", doc_date=TODAY - timedelta(days=10), section_id=i[sec], work_type_id=i["wt"], status="issued")
                db.add(doc)
                await db.flush()
                db.add(TmcDocumentItem(document_id=doc.id, nomenclature_id=i["n1"], name="x", qty=Decimal(qty), price=Decimal("100")))
            for key, role, sec in (("uAdmin", "admin", None), ("uA", "master", "secA"), ("uB", "master", "secB"), ("uC", "master", "secC")):
                db.add(User(id=i[key], email=f"pa-{key}-{tag}@example.test", full_name=key, role=role, section_id=i[sec] if sec else None, **ad_user()))
            await db.commit()
        return self

    def u(self, key, role="master", sec=None):
        return User(id=self.ids[key], email="x", full_name=key, role=role, section_id=self.ids[sec] if sec else None)

    async def cleanup(self):
        i = self.ids
        async with SessionFactory() as db:
            await db.execute(delete(TmcDocument).where(TmcDocument.doc_no.like(f"%-{self.tag}")))
            await db.execute(delete(MaintenancePlan).where(MaintenancePlan.asset_id.in_([i["a1"], i["a2"]])))
            await db.execute(delete(FixedAsset).where(FixedAsset.id.in_([i["a1"], i["a2"]])))
            await db.execute(delete(Nomenclature).where(Nomenclature.name.like(f"%-{self.tag}")))
            await db.execute(delete(MaintenanceInterval).where(MaintenanceInterval.id == i["iv"]))
            await db.execute(delete(WorkType).where(WorkType.id == i["wt"]))
            await db.execute(delete(User).where(User.id.in_([i["uAdmin"], i["uA"], i["uB"], i["uC"]])))
            await db.execute(delete(Section).where(Section.id.in_([i["secA"], i["secB"], i["secC"]])))
            await db.execute(delete(Department).where(Department.id == i["d_two"]))
            if self.made_dept:
                await db.execute(delete(Department).where(Department.id == i["d_pol"]))
            await db.commit()


@pytest_asyncio.fixture
async def w():
    world = await World().seed()
    yield world
    await world.cleanup()


def _item(result, key, value):
    return next(x for x in result["items"] if x[key] == value)


async def test_repair_forecast_counts_open_rows_and_scopes_the_master(w):
    admin, a, b = w.u("uAdmin", "admin"), w.u("uA", sec="secA"), w.u("uB", sec="secB")
    async with SessionFactory() as db:
        r = await svc.repair_forecast(db, admin, horizon="quarter", section_id=None, include_cycles=False, upcoming_limit=100000)
        item = _item(r, "interval_code", f"I-{w.tag}")
        assert item["planned"] == 2 and item["projected"] == 0 and item["by_asset_type"]["diesel"] == 2
        assert item["by_age"] == {"new": 1, "middle": 0, "old": 1, "unknown": 0}
        assert {u["inv_number"] for u in r["upcoming"]} >= {f"PA1-{w.tag}", f"PA2-{w.tag}"}
        cyc = await svc.repair_forecast(db, admin, horizon="quarter", section_id=None, include_cycles=True)
        assert _item(cyc, "interval_code", f"I-{w.tag}")["total"] == 3 + 2  # a1: +10,+50,+90; a2: +20,+60
        mine = await svc.repair_forecast(db, a, horizon="quarter", section_id=None, include_cycles=False, upcoming_limit=100000)
        assert _item(mine, "interval_code", f"I-{w.tag}")["planned"] == 1
        assert any(u["inv_number"] == f"PA1-{w.tag}" for u in mine["upcoming"]) and all(u["inv_number"] != f"PA2-{w.tag}" for u in mine["upcoming"])
        with pytest.raises(HTTPException) as exc:
            await svc.repair_forecast(db, a, horizon="quarter", section_id=w.ids["secB"], include_cycles=False)
        assert exc.value.status_code == 404
        assert _item(await svc.repair_forecast(db, b, horizon="year", section_id=w.ids["secB"], include_cycles=False), "interval_code", f"I-{w.tag}")["by_age"]["old"] == 1


async def test_parts_demand_is_plan_times_norm_and_history_average(w):
    admin, a = w.u("uAdmin", "admin"), w.u("uA", sec="secA")
    async with SessionFactory() as db:
        r = await svc.parts_demand(db, admin, horizon="all", section_id=None, include_cycles=False, limit=1000, offset=0)
        it = _item(r, "nomenclature_id", w.ids["n1"])
        assert (it["qty_quarter"], it["qty_year"], it["cost_quarter"]) == (4.0, 4.0, 400.0)
        assert it["history_monthly_avg"] == pytest.approx(8 / 6, abs=1e-3) and it["note"] is None
        mine = _item(await svc.parts_demand(db, a, horizon="quarter", section_id=None, include_cycles=False, limit=1000, offset=0), "nomenclature_id", w.ids["n1"])
        assert mine["qty_quarter"] == 2.0 and mine["history_monthly_avg"] == pytest.approx(5 / 6, abs=1e-3)
        with pytest.raises(HTTPException) as exc:
            await svc.parts_demand(db, a, horizon="all", section_id=w.ids["secB"], include_cycles=False, limit=10, offset=0)
        assert exc.value.status_code == 404


async def test_consumption_overuse_is_quantity_above_the_norm(w):
    admin, a = w.u("uAdmin", "admin"), w.u("uA", sec="secA")
    async with SessionFactory() as db:
        r = await svc.parts_consumption(db, admin, months=3, section_id=None, limit=500)
        it = _item(r, "nomenclature_id", w.ids["n1"])
        assert it["total_qty"] == 8.0 and it["over_qty"] == 4.0 and it["over_cost"] == 400.0 and it["top_work_types"][0]["work_type"] == f"W-{w.tag}"
        assert len(it["series"]) == 3 and it["trend"] is None
        mine = _item(await svc.parts_consumption(db, a, months=3, section_id=None, limit=500), "nomenclature_id", w.ids["n1"])
        assert mine["total_qty"] == 5.0 and mine["over_qty"] == 3.0
        with pytest.raises(HTTPException) as exc:
            await svc.parts_consumption(db, a, months=3, section_id=w.ids["secB"], limit=5)
        assert exc.value.status_code == 404


async def _risk(db, user, **kw):
    return await svc.stock_risk(db, user, section_id=kw.pop("section_id", None), status=kw.pop("status", None), sort_by=kw.pop("sort_by", "status"), sort_dir="asc", limit=1000, offset=0, include_cycles=False)


async def test_stock_risk_statuses_follow_stock_orders_and_lead_time(w):
    admin, c = w.u("uAdmin", "admin"), w.u("uC", sec="secC")
    n1 = w.ids["n1"]
    async with SessionFactory() as db:
        assert _item(await _risk(db, admin), "nomenclature_id", n1)["status"] == "no_data"
        db.add(StockBalance(nomenclature_id=n1, warehouse="W1", qty=Decimal(10), as_of=TODAY, source="manual"))
        db.add(SupplierTerm(nomenclature_id=n1, lead_time_days=30, safety_days=14))
        await db.commit()
        it = _item(await _risk(db, admin), "nomenclature_id", n1)
        # daily = max(8 issued / 180 days, 4 planned / 90 days) = 0.0444; 10 pieces last 225 days
        assert it["status"] == "ok" and it["runs_out_in_days"] == 225 and it["lead_time_unknown"] is False and it["stock"] == 10.0
        await db.execute(delete(StockBalance).where(StockBalance.nomenclature_id == n1))
        db.add(StockBalance(nomenclature_id=n1, warehouse="W1", qty=Decimal(1), as_of=TODAY, source="manual"))
        await db.commit()
        it = _item(await _risk(db, admin), "nomenclature_id", n1)
        assert it["status"] == "critical" and it["runs_out_in_days"] == 22 and "Остаток 1 шт" in it["message"]
        db.add(PurchaseOrder(nomenclature_id=n1, qty=Decimal(5), qty_received=Decimal(1), status="partial", expected_on=TODAY + timedelta(days=10)))
        db.add(PurchaseOrder(nomenclature_id=n1, qty=Decimal(500), status="cancelled", expected_on=TODAY + timedelta(days=5)))
        await db.commit()
        it = _item(await _risk(db, admin), "nomenclature_id", n1)
        assert it["open_orders_qty"] == 4.0 and it["order_arrives_in_days"] == 10 and it["status"] != "critical"
        assert it["coverage"]["year"]["covers"] is False and it["shortfall_cost_year"] > 0
        filtered = await _risk(db, admin, status=it["status"])
        assert all(x["status"] == it["status"] for x in filtered["items"]) and filtered["total"] == len(filtered["items"])
        assert set(filtered["summary"]) >= {"critical", "order_now", "ok", "no_data", "shortfall_cost_quarter", "shortfall_cost_half", "shortfall_cost_year"}
        # a master of a section that never used the part does not see it; the stock is not scoped, the part list is
        assert all(x["nomenclature_id"] != n1 for x in (await _risk(db, c))["items"])
        a = w.u("uA", sec="secA")
        assert any(x["nomenclature_id"] == n1 for x in (await _risk(db, a))["items"])
        with pytest.raises(HTTPException) as exc:
            await _risk(db, a, section_id=w.ids["secB"], sort_by="bogus")  # 404 comes before the 422
        assert exc.value.status_code == 404
        with pytest.raises(HTTPException) as exc:
            await _risk(db, admin, sort_by="bogus")
        assert exc.value.status_code == 422


def _csv(*lines):
    return ("\n".join(lines) + "\n").encode("utf-8")


async def test_import_is_dry_run_first_then_upserts_and_reports_unmatched(w):
    n1 = w.ids["n1"]
    stock_csv = _csv("Номенклатура;Код;Склад;Единица;Количество", f"x;C-{w.tag};Склад 1;шт;7", f"x;C-{w.tag};Склад 1;шт;3", f"Дубль-{w.tag};;Склад 1;шт;4", f"Нет-такого-{w.tag};;Склад 1;шт;1")
    async with SessionFactory() as db:
        rep = await si.import_file(db, stock_csv, "s.csv", apply=False, as_of=TODAY)
    sheet = rep["sheets"][0]
    assert rep["applied"] is False and sheet["kind"] == "stock" and sheet["matched"] == 2 and sheet["would_write"] == 2
    assert sheet["not_found_count"] == 1 and sheet["ambiguous_count"] == 1
    async with SessionFactory() as db:
        assert (await db.execute(select(StockBalance).where(StockBalance.nomenclature_id == n1))).first() is None
    for _ in range(2):  # twice: the second run updates the same row (upsert key nomenclature + warehouse + date)
        async with SessionFactory() as db:
            rep = await si.import_file(db, stock_csv, "s.csv", apply=True, as_of=TODAY)
        assert rep["sheets"][0]["written"] == 1 + 0 or rep["sheets"][0]["written"] == 1
    async with SessionFactory() as db:
        rows = (await db.execute(select(StockBalance).where(StockBalance.nomenclature_id == n1))).scalars().all()
        assert len(rows) == 1 and rows[0].qty == Decimal("10.000") and rows[0].source == "1c_import" and rows[0].batch_id is not None
    orders_csv = _csv("Номенклатура;Код;Поставщик;Количество;Дата заказа;Ожидаемая дата;Номер", f"x;C-{w.tag};ООО Тест;6;01.11.2026;15.12.2026;ЗП-{w.tag}")
    leads_csv = _csv("Номенклатура;Код;Срок поставки, дней;Поставщик", f"x;C-{w.tag};75;ООО Тест")
    for content in (orders_csv, orders_csv, leads_csv):
        async with SessionFactory() as db:
            rep = await si.import_file(db, content, "o.csv", apply=True)
    async with SessionFactory() as db:
        orders = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.nomenclature_id == n1))).scalars().all()
        assert len(orders) == 1 and orders[0].doc_no == f"ЗП-{w.tag}" and orders[0].status == "ordered"
        term = (await db.execute(select(SupplierTerm).where(SupplierTerm.nomenclature_id == n1))).scalar_one()
        assert term.lead_time_days == 75 and term.safety_days == 14


async def test_terms_and_orders_crud_validation_and_master_scope(w):
    n1 = w.ids["n1"]
    admin, a, c = w.u("uAdmin", "admin"), w.u("uA", sec="secA"), w.u("uC", sec="secC")
    async with SessionFactory() as db:
        t = await stock_svc.put_term(db, n1, SupplierTermWrite(supplier="S", lead_time_days=20))
        assert t["lead_time_days"] == 20 and t["safety_days"] == 14
        t = await stock_svc.put_term(db, n1, SupplierTermWrite(supplier="S2", lead_time_days=25, safety_days=3))
        assert (t["supplier"], t["lead_time_days"], t["safety_days"]) == ("S2", 25, 3)
        with pytest.raises(HTTPException) as exc:
            await stock_svc.put_term(db, uuid4(), SupplierTermWrite(lead_time_days=5))
        assert exc.value.status_code == 404
        with pytest.raises(HTTPException) as exc:
            await stock_svc.create_order(db, PurchaseOrderCreate(nomenclature_id=n1, qty=Decimal(5), qty_received=Decimal(6)))
        assert exc.value.status_code == 422
        with pytest.raises(HTTPException) as exc:
            await stock_svc.create_order(db, PurchaseOrderCreate(nomenclature_id=n1, qty=Decimal(5), ordered_on=TODAY, expected_on=TODAY - timedelta(days=1)))
        assert exc.value.status_code == 422
        o = await stock_svc.create_order(db, PurchaseOrderCreate(nomenclature_id=n1, qty=Decimal(5), expected_on=TODAY + timedelta(days=9), doc_no=f"X-{w.tag}"))
        o2 = await stock_svc.put_order(db, o["id"], PurchaseOrderWrite(qty=Decimal(5), qty_received=Decimal(5), status="received"))
        assert o2["status"] == "received"
        items, total = await stock_svc.list_orders(db, admin, nomenclature_id=n1, status=None, open_only=True, sort_by="expected_on", sort_dir="asc", limit=10, offset=0)
        assert total == 0
        items, total = await stock_svc.list_orders(db, a, nomenclature_id=n1, status=None, open_only=False, sort_by="expected_on", sort_dir="asc", limit=10, offset=0)
        assert total == 1
        items, total = await stock_svc.list_orders(db, c, nomenclature_id=n1, status=None, open_only=False, sort_by="expected_on", sort_dir="desc", limit=10, offset=0)
        assert total == 0  # a master of a section that never used the part sees nothing
        _, total = await stock_svc.list_terms(db, c, nomenclature_id=n1, limit=10, offset=0)
        assert total == 0
        with pytest.raises(HTTPException) as exc:
            await stock_svc.list_orders(db, admin, nomenclature_id=None, status=None, open_only=False, sort_by="bogus", sort_dir="asc", limit=1, offset=0)
        assert exc.value.status_code == 422
