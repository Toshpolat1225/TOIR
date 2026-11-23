"""Work order automation on PostgreSQL: planned start/end defaults from the repair-type duration,
actual start/end stamped by the server on status changes, creator/editor audit with names (needs pg_rehearse)."""
from user_factory import ad_user
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import delete

from app.core.database import SessionFactory
from app.models.assets import FixedAsset
from app.models.identity import User
from app.models.maintenance import WorkType
from app.models.organization import Employee, Section
from app.models.work_orders import WorkOrder
from app.schemas.references import WorkTypeCreate
from app.schemas.work_orders import WorkOrderCreate, WorkOrderRepairInput, WorkOrderUpdate
from app.services import work_orders

pytestmark = [pytest.mark.pg, pytest.mark.asyncio]


class World:
    def __init__(self):
        self.tag = uuid4().hex[:8]
        self.section_id, self.asset_id, self.employee_id = uuid4(), uuid4(), uuid4()
        self.creator_id, self.editor_id = uuid4(), uuid4()
        self.four, self.two_half, self.none = uuid4(), uuid4(), uuid4()

    async def seed(self):
        async with SessionFactory() as db:
            db.add(Section(id=self.section_id, name=f"S-{self.tag}"))
            await db.flush()
            db.add(FixedAsset(id=self.asset_id, inv_number=f"LC-{self.tag}", asset_type="locomotive",
                              status="operational", mileage=Decimal("100"), section_id=self.section_id))
            db.add(Employee(id=self.employee_id, tab_number=f"T{self.tag}", full_name=f"Исполнитель {self.tag}", section_id=self.section_id))
            for uid, name in ((self.creator_id, "Создатель"), (self.editor_id, "Редактор")):
                db.add(User(id=uid, email=f"{name.lower()}-{self.tag}@test.local", full_name=f"{name} {self.tag}",
                            role="admin", **ad_user(), is_active=True))
            for wid, code, hours in ((self.four, "A", Decimal("4")), (self.two_half, "B", Decimal("2.5")), (self.none, "C", None)):
                db.add(WorkType(id=wid, code=f"{code}-{self.tag}", name=f"тип {code}", unit_type="locomotive", duration_hours=hours))
            await db.commit()
        return self

    def user(self, which="creator"):
        return SimpleNamespace(id=self.creator_id if which == "creator" else self.editor_id, role="admin", section_id=None)

    def payload(self, *types, **extra):
        return WorkOrderCreate(
            fixed_asset_id=self.asset_id, order_kind="unplanned", executor_id=self.employee_id,
            description="проверка", repairs=[WorkOrderRepairInput(work_type_id=t) for t in types], **extra,
        )

    async def cleanup(self):
        async with SessionFactory() as db:
            await db.execute(delete(WorkOrder).where(WorkOrder.fixed_asset_id == self.asset_id))
            await db.execute(delete(FixedAsset).where(FixedAsset.id == self.asset_id))
            await db.execute(delete(WorkType).where(WorkType.id.in_([self.four, self.two_half, self.none])))
            await db.execute(delete(Employee).where(Employee.id == self.employee_id))
            await db.execute(delete(User).where(User.id.in_([self.creator_id, self.editor_id])))
            await db.execute(delete(Section).where(Section.id == self.section_id))
            await db.commit()


@pytest_asyncio.fixture
async def world():
    w = await World().seed()
    try:
        yield w
    finally:
        await w.cleanup()


async def test_planned_times_are_filled_from_the_repair_type_durations(world):
    before = datetime.now(timezone.utc)
    async with SessionFactory() as db:
        order = await work_orders.create_order(db, world.user(), world.payload(world.four, world.two_half))
    assert before - timedelta(seconds=2) <= order.date_start <= datetime.now(timezone.utc) + timedelta(seconds=2)
    assert order.date_end - order.date_start == timedelta(hours=6.5)
    assert order.planned_hours == Decimal("6.5")
    assert [r.duration_hours for r in order.repairs] == [Decimal("4.00"), Decimal("2.50")]


async def test_no_planned_end_is_invented_when_a_duration_is_missing(world):
    async with SessionFactory() as db:
        order = await work_orders.create_order(db, world.user(), world.payload(world.four, world.none))
    assert order.date_start is not None
    assert order.date_end is None
    assert order.planned_hours is None


async def test_explicit_planned_times_win_and_bad_order_is_rejected(world):
    start = datetime.now(timezone.utc) + timedelta(days=1)
    end = start + timedelta(hours=1)
    async with SessionFactory() as db:
        order = await work_orders.create_order(db, world.user(), world.payload(world.four, date_start=start, date_end=end))
    assert order.date_start == start and order.date_end == end
    with pytest.raises(ValueError):
        world.payload(world.four, date_start=end, date_end=start)
    async with SessionFactory() as db:
        with pytest.raises(HTTPException) as caught:
            await work_orders.create_order(
                db, world.user(), world.payload(world.four, date_end=datetime.now(timezone.utc) - timedelta(days=1))
            )
    assert caught.value.status_code == 422


async def test_creator_editor_and_actual_times_are_stamped_by_the_server(world):
    async with SessionFactory() as db:
        order = await work_orders.create_order(db, world.user("creator"), world.payload(world.four))
    assert order.created_by == world.creator_id and order.created_by_name == f"Создатель {world.tag}"
    assert order.updated_by == world.creator_id
    assert order.actual_start is None and order.actual_end is None

    async with SessionFactory() as db:
        started = await work_orders.update_order(db, world.user("editor"), order.id, WorkOrderUpdate(status="in_progress"))
    assert started.actual_start is not None and started.actual_end is None
    assert started.updated_by == world.editor_id and started.updated_by_name == f"Редактор {world.tag}"
    assert started.created_by_name == f"Создатель {world.tag}"

    async with SessionFactory() as db:
        done = await work_orders.update_order(db, world.user("creator"), order.id, WorkOrderUpdate(status="completed"))
    assert done.actual_start == started.actual_start
    assert done.actual_end is not None and done.actual_end == done.closed_at
    assert done.actual_end >= done.actual_start
    assert done.updated_by_name == f"Создатель {world.tag}"


async def test_a_plain_edit_does_not_stamp_actual_times(world):
    async with SessionFactory() as db:
        order = await work_orders.create_order(db, world.user(), world.payload(world.four))
    async with SessionFactory() as db:
        edited = await work_orders.update_order(db, world.user("editor"), order.id, WorkOrderUpdate(note="правка"))
    assert edited.actual_start is None and edited.actual_end is None
    assert edited.updated_by == world.editor_id


async def test_work_type_duration_is_validated():
    assert WorkTypeCreate(code="X", name="x", unit_type="wagon", duration_hours=Decimal("2.5")).duration_hours == Decimal("2.5")
    assert WorkTypeCreate(code="X", name="x", unit_type="wagon").duration_hours is None
    for bad in (Decimal("0"), Decimal("-1")):
        with pytest.raises(ValueError):
            WorkTypeCreate(code="X", name="x", unit_type="wagon", duration_hours=bad)
