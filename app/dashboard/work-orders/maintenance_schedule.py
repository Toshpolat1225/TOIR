from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from ..database import get_db
from ..repositories.work_order import WorkOrderRepository
from ..repositories.maintenance_plan import MaintenancePlanRepository
from ..repositories.fixed_asset import FixedAssetRepository
from ..repositories.maintenance_interval import MaintenanceIntervalRepository
from ..schemas.maintenance_schedule import ScheduleItem

AVG_KM_PER_DAY = 10


class MaintenanceScheduleService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.work_order_repo = WorkOrderRepository(db)
        self.plan_repo = MaintenancePlanRepository(db)
        self.asset_repo = FixedAssetRepository(db)
        self.interval_repo = MaintenanceIntervalRepository(db)

    def _to_dd_mm_yyyy(self, d: date | None) -> str:
        if not d:
            return ""
        return d.strftime("%d.%m.%Y")

    def _next_trigger_km(self, current_mileage: int, interval_km: int) -> int:
        if interval_km <= 0:
            return current_mileage
        return (current_mileage // interval_km + 1) * interval_km

    async def get_schedule(self, month_str: str | None) -> list[ScheduleItem]:
        now = date.today()
        year, month = now.year, now.month

        if month_str:
            try:
                y, m = map(int, month_str.split("-"))
                if 1 <= m <= 12:
                    year, month = y, m
            except (ValueError, IndexError):
                pass  # Keep default if format is wrong

        range_start = date(year, month, 1)
        today = date.today()

        # 1. Fetch all required data in parallel
        wo_data, _ = await self.work_order_repo.list(limit=500, offset=0)
        plan_data, _ = await self.plan_repo.list(
            limit=1000, offset=0, status__in=["Scheduled", "InProgress"]
        )
        assets_data, _ = await self.asset_repo.list(
            limit=1000, offset=0, asset_type__in=["locomotive", "diesel"]
        )
        intervals_data, _ = await self.interval_repo.list(
            limit=1000, offset=0, is_active=True
        )

        asset_mileage = {asset.id: asset.mileage or 0 for asset in assets_data}
        asset_depot = {asset.id: asset.depot or "" for asset in assets_data}
        mileage_by_unit = {asset.name.strip(): asset.mileage or 0 for asset in assets_data}

        # 2. Process existing Work Orders
        wo_status_map = {
            "pending": "upcoming",
            "in_progress": "in_progress",
            "completed": "completed",
        }
        today_str = self._to_dd_mm_yyyy(today)
        wo_items = [
            ScheduleItem(
                id=str(wo.id),
                unit=wo.unit or "",
                type=wo.repair_kind or wo.work_type or "ТО",
                startDate=self._to_dd_mm_yyyy(wo.date_start) or today_str,
                durationH=8,
                depot=wo.section or wo.depot or "",
                tech=wo.tech or "",
                status=wo_status_map.get(wo.status, "upcoming"),
                note=wo.note,
                mileage=mileage_by_unit.get((wo.unit or "").strip()),
            )
            for wo in wo_data
        ]

        # 3. Process planned maintenance
        plan_items = []
        for mp in plan_data:
            trigger = mp.trigger_mileage or 0
            current_mileage = asset_mileage.get(mp.asset_id, 0)
            remaining_km = trigger - current_mileage
            status = "in_progress" if mp.status == "InProgress" else "overdue" if remaining_km < 0 else "upcoming"
            plan_items.append(
                ScheduleItem(
                    id=f"plan-{mp.id}",
                    unit=mp.asset_name or "",
                    type=mp.maintenance_type or "ТО",
                    startDate=self._to_dd_mm_yyyy(mp.scheduled_date) or today_str,
                    durationH=8,
                    depot=asset_depot.get(mp.asset_id, ""),
                    tech="",
                    status=status,
                    mileage=current_mileage,
                    remainingKm=max(0, remaining_km),
                    nextThreshold=trigger,
                )
            )

        # 4. Calculate future maintenance from intervals
        existing_plan_keys = {
            f"{mp.asset_id}-{mp.maintenance_type}-{mp.trigger_mileage}" for mp in plan_data
        }
        raw_interval_items = []
        for asset in assets_data:
            mileage = asset.mileage or 0
            asset_types = [asset.asset_type] if asset.asset_type else ["locomotive", "diesel"]
            for interval in intervals_data:
                if not interval.interval_km:
                    continue
                interval_asset_types = interval.asset_types or ["locomotive", "diesel"]
                if not any(t in interval_asset_types for t in asset_types):
                    continue

                next_tr = self._next_trigger_km(mileage, interval.interval_km)
                key = f"{asset.id}-{interval.code}-{next_tr}"
                if key in existing_plan_keys:
                    continue

                remaining_km = next_tr - mileage
                raw_interval_items.append(
                    ScheduleItem(
                        id=f"interval-{key}",
                        unit=asset.name or "",
                        type=interval.code or interval.name,
                        startDate=today_str,
                        durationH=8,
                        depot=asset.depot or "",
                        tech="",
                        status="upcoming",
                        mileage=mileage,
                        remainingKm=max(0, remaining_km),
                        nextThreshold=next_tr,
                    )
                )

        # 5. Assign dates to calculated items
        overdue_or_due = sorted([i for i in raw_interval_items if (i.remainingKm or 0) <= 0], key=lambda x: (x.mileage or 0) - (x.nextThreshold or 0), reverse=True)
        future = sorted([i for i in raw_interval_items if (i.remainingKm or 0) > 0], key=lambda x: x.remainingKm or 0)

        due_items = [item.model_copy(update={"startDate": self._to_dd_mm_yyyy(range_start + timedelta(days=min(i, 6))), "status": "overdue" if (item.remainingKm or 0) < 0 else "upcoming"}) for i, item in enumerate(overdue_or_due)]
        future_items = [item.model_copy(update={"startDate": self._to_dd_mm_yyyy(today + timedelta(days=max(1, (item.remainingKm or 0) // AVG_KM_PER_DAY)))}) for item in future]

        return wo_items + plan_items + due_items + future_items


def get_maintenance_schedule_service(db: AsyncSession = Depends(get_db)) -> MaintenanceScheduleService:
    return MaintenanceScheduleService(db)