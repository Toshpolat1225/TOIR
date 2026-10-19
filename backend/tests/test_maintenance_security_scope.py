import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from app.repositories import maintenance as maintenance_repository
from app.schemas.maintenance import MaintenancePlanUpdate
from app.schemas.users import UserUpdate
from app.schemas.work_orders import WorkOrderCreate, WorkOrderRepairInput
from app.services import maintenance, users, work_orders


class MaintenanceScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_schedule_asset_query_is_filtered_in_sql(self):
        db = Mock()
        result = Mock()
        result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result)
        section_id = uuid4()
        await maintenance_repository.list_schedule_assets(
            db, master_section_id=section_id
        )
        query = str(db.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
        self.assertIn("fixed_assets.section_id", query)

    async def test_plan_lookup_query_joins_asset_and_filters_section(self):
        db = Mock()
        result = Mock()
        result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)
        await maintenance_repository.get_plan(
            db, uuid4(), master_section_id=uuid4()
        )
        query = str(db.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
        self.assertIn("fixed_assets.section_id", query)

    async def test_schedule_work_orders_filter_order_and_asset_section(self):
        db = Mock()
        result = Mock()
        result.all.return_value = []
        db.execute = AsyncMock(return_value=result)
        await maintenance_repository.list_work_orders_for_schedule(
            db, start=date(2026, 10, 1), end=date(2026, 11, 1),
            master_section_id=uuid4(),
        )
        query = str(db.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
        self.assertIn("work_orders.section_id", query)
        self.assertIn("fixed_assets.section_id", query)

    async def test_master_plan_list_uses_authenticated_section(self):
        section_id = uuid4()
        user = SimpleNamespace(role="master", section_id=section_id)
        with patch.object(
            maintenance.repository, "list_plans", new=AsyncMock(return_value=([], 0))
        ) as list_plans:
            rows, total = await maintenance.list_plans(
                Mock(), user, asset_id=uuid4(), status_filter=None,
                month=None, limit=20, offset=0,
            )
        self.assertEqual((rows, total), ([], 0))
        self.assertEqual(list_plans.await_args.kwargs["master_section_id"], section_id)

    async def test_master_without_section_is_rejected_before_queries(self):
        user = SimpleNamespace(role="master", section_id=None)
        db = Mock()
        with self.assertRaises(HTTPException) as raised:
            await maintenance.list_plans(
                db, user, asset_id=None, status_filter=None,
                month=None, limit=20, offset=0,
            )
        self.assertEqual(raised.exception.status_code, 403)

    async def test_master_schedule_scopes_orders_plans_and_assets(self):
        section_id = uuid4()
        user = SimpleNamespace(role="master", section_id=section_id)
        with (
            patch.object(maintenance, "get_daily_average_km", new=AsyncMock(return_value=None)),
            patch.object(maintenance.repository, "list_work_orders_for_schedule", new=AsyncMock(return_value=[])) as orders,
            patch.object(maintenance.repository, "list_plans", new=AsyncMock(return_value=([], 0))) as plans,
            patch.object(maintenance.repository, "list_asset_interval_plans", new=AsyncMock(return_value={})) as interval_plans,
            patch.object(maintenance.repository, "list_schedule_assets", new=AsyncMock(return_value=[])) as assets,
        ):
            await maintenance.get_schedule(Mock(), user, "2026-10")
        self.assertEqual(orders.await_args.kwargs["master_section_id"], section_id)
        self.assertEqual(plans.await_args.kwargs["master_section_id"], section_id)
        self.assertEqual(interval_plans.await_args.kwargs["master_section_id"], section_id)
        self.assertEqual(assets.await_args.kwargs["master_section_id"], section_id)

    async def test_cross_section_plan_update_is_404_before_status_checks(self):
        user = SimpleNamespace(role="master", section_id=uuid4())
        db = Mock()
        with patch.object(
            maintenance.repository, "get_plan", new=AsyncMock(return_value=None)
        ) as get_plan:
            with self.assertRaises(HTTPException) as raised:
                await maintenance.update_plan(
                    db, user, uuid4(), MaintenancePlanUpdate(status="completed")
                )
        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(get_plan.await_args.kwargs["master_section_id"], user.section_id)
        db.commit.assert_not_awaited()

    async def test_cross_section_linked_work_order_is_404_before_plan_status(self):
        section_id = uuid4()
        user = SimpleNamespace(role="master", section_id=section_id)
        plan = SimpleNamespace(id=uuid4(), asset_id=uuid4(), status="scheduled")
        db = Mock()
        with (
            patch.object(maintenance.repository, "get_plan", new=AsyncMock(return_value=plan)),
            patch("app.repositories.work_orders.get_order", new=AsyncMock(return_value=None)) as get_order,
        ):
            with self.assertRaises(HTTPException) as raised:
                await maintenance.update_plan(
                    db, user, plan.id,
                    MaintenancePlanUpdate(work_order_id=uuid4(), status="completed"),
                )
        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(get_order.await_args.kwargs["master_section_id"], section_id)
        db.commit.assert_not_awaited()

    async def test_master_cannot_create_order_from_another_sections_plan(self):
        section_id = uuid4()
        user = SimpleNamespace(role="master", section_id=section_id, id=uuid4())
        payload = WorkOrderCreate(
            fixed_asset_id=uuid4(), maintenance_plan_id=uuid4(),
            order_kind="planned", executor_id=uuid4(), description="test",
            repairs=[WorkOrderRepairInput(work_type_id=uuid4())],
        )
        with (
            patch.object(work_orders.maintenance_repository, "get_plan", new=AsyncMock(return_value=None)) as get_plan,
            patch.object(work_orders, "_resolve_create_scope", new=AsyncMock()) as resolve_scope,
        ):
            with self.assertRaises(HTTPException) as raised:
                await work_orders.create_order(Mock(), user, payload)
        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(get_plan.await_args.kwargs["master_section_id"], section_id)
        resolve_scope.assert_not_awaited()


class AdminRoleProtectionTests(unittest.IsolatedAsyncioTestCase):
    async def _update_admin(self, *, active_admin_count, changes):
        user_id = uuid4()
        target = SimpleNamespace(
            id=user_id, role="admin", is_active=True, section_id=None,
        )
        db = Mock()
        count_result = Mock()
        count_result.scalar_one.return_value = active_admin_count
        db.execute = AsyncMock(side_effect=[Mock(), count_result])
        db.rollback = AsyncMock()
        with patch.object(users, "get_user", new=AsyncMock(return_value=target)):
            await users.update_user(db, user_id, UserUpdate(**changes), uuid4())

    async def test_admin_demote_is_blocked_even_when_another_admin_exists(self):
        with self.assertRaises(HTTPException) as raised:
            await self._update_admin(active_admin_count=2, changes={"role": "operator"})
        self.assertEqual(raised.exception.status_code, 403)

    async def test_last_active_admin_cannot_be_deactivated(self):
        with self.assertRaises(HTTPException) as raised:
            await self._update_admin(active_admin_count=1, changes={"is_active": False})
        self.assertEqual(raised.exception.status_code, 409)

    async def test_last_active_admin_cannot_be_demoted(self):
        with self.assertRaises(HTTPException) as raised:
            await self._update_admin(active_admin_count=1, changes={"role": "operator"})
        self.assertEqual(raised.exception.status_code, 409)

    async def test_user_cannot_deactivate_self(self):
        user_id = uuid4()
        target = SimpleNamespace(
            id=user_id, role="operator", is_active=True, section_id=None,
        )
        db = Mock()
        db.execute = AsyncMock()
        db.rollback = AsyncMock()
        with patch.object(users, "get_user", new=AsyncMock(return_value=target)):
            with self.assertRaises(HTTPException) as raised:
                await users.update_user(
                    db, user_id, UserUpdate(is_active=False), user_id
                )
        self.assertEqual(raised.exception.status_code, 409)

    async def test_non_admin_role_update_remains_allowed(self):
        user_id = uuid4()
        target = SimpleNamespace(
            id=user_id, role="master", is_active=True, section_id=uuid4(),
        )
        db = Mock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        with patch.object(users, "get_user", new=AsyncMock(return_value=target)):
            updated = await users.update_user(
                db, user_id, UserUpdate(role="operator"), uuid4()
            )
        self.assertIs(updated, target)
        self.assertEqual(updated.role, "operator")
        db.commit.assert_awaited_once()
