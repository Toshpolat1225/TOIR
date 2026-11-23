"""Benign same-time counter advance, counter release, leading-zero number conflicts."""
from user_factory import ad_user
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core.database import SessionFactory
from app.models.asset_field_changes import AssetFieldChange
from app.models.assets import FixedAsset
from app.models.audit_log import AuditLog
from app.models.identity import User
from app.models.mileage import WialonOdometerReading
from app.models.wialon_counters import WialonCounterState
from app.services import asset_field_changes as field_changes
from app.services import wialon_counter_release as release
from app.services import wialon_ingestion
from app.services.wialon_quality import COUNTER_ADVANCED_REASON, is_counter_advance

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


# ------------------------------------------------------------ pure rule

def test_higher_value_with_the_same_message_time_is_a_benign_advance():
    first_seen = T0
    assert is_counter_advance([(Decimal("100"), first_seen)], Decimal("103"), T0 + timedelta(minutes=6))
    # grows more slowly than the maximum speed: 27 km in 99 minutes is fine
    assert is_counter_advance([(Decimal("100"), first_seen)], Decimal("127"), T0 + timedelta(minutes=99))


def test_lower_equal_unknown_time_or_too_fast_growth_is_a_real_conflict():
    seen = T0
    later = T0 + timedelta(minutes=6)
    assert not is_counter_advance([(Decimal("100"), seen)], Decimal("99"), later)  # decreased
    assert not is_counter_advance([(Decimal("100"), seen)], Decimal("100"), later)  # not higher
    assert not is_counter_advance([(Decimal("100"), None)], Decimal("103"), later)  # unknown receipt
    assert not is_counter_advance([], Decimal("103"), later)
    # 37 km in 4 minutes is 555 km/h: impossible
    assert not is_counter_advance([(Decimal("100"), seen)], Decimal("137"), T0 + timedelta(minutes=4))
    # one earlier value higher than the new one: counter went backwards
    assert not is_counter_advance(
        [(Decimal("100"), seen), (Decimal("105"), seen)], Decimal("103"), later
    )


def _ingest_db(rows, new_reading):
    calls = 0

    async def execute(_statement):
        nonlocal calls
        calls += 1
        if calls < 4:
            return SimpleNamespace(
                scalar_one_or_none=lambda: new_reading if calls == 3 else None
            )
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))

    return SimpleNamespace(add=Mock(), execute=AsyncMock(side_effect=execute), flush=AsyncMock())


@pytest.mark.asyncio
async def test_ingestion_does_not_block_the_counter_on_a_benign_advance():
    old = SimpleNamespace(
        id=1, odometer_km=Decimal("100"), received_at=T0,
        calculation_eligible=True, classification="CONFIRMED", rejection_reason=None,
    )
    new = SimpleNamespace(
        id=2, odometer_km=Decimal("103"), received_at=T0 + timedelta(minutes=6),
        calculation_eligible=False, classification="HELD", rejection_reason=None,
    )
    state = SimpleNamespace(last_status="accepted", last_reason=None)
    with (
        patch.object(wialon_ingestion.counters_repository, "get_asset_by_wialon_id",
                     new=AsyncMock(return_value=SimpleNamespace(id="a1"))),
        patch.object(wialon_ingestion.counters_repository, "get_state_row",
                     new=AsyncMock(return_value=state)),
        patch.object(wialon_ingestion.counters_repository, "mark_conflict", new=AsyncMock()) as mark,
        patch.object(wialon_ingestion.counters_repository, "save_decision", new=AsyncMock()) as save,
    ):
        result = await wialon_ingestion.ingest_wialon_reading(
            _ingest_db([old, new], new),
            unit_id="w-1", odometer_km=Decimal("103"), reading_at=T0,
            received_at=T0 + timedelta(minutes=6), transport="pull", source_time_verified=True,
        )
    mark.assert_not_awaited()
    save.assert_not_awaited()
    assert state.last_reason is None  # the counter is NOT blocked
    assert result.reason == COUNTER_ADVANCED_REASON
    assert result.calculation_eligible is False and result.classification == "HELD"
    assert old.calculation_eligible is True and old.rejection_reason is None  # representative kept


@pytest.mark.asyncio
async def test_ingestion_still_blocks_when_the_later_value_is_lower():
    old = SimpleNamespace(
        id=1, odometer_km=Decimal("110"), received_at=T0,
        calculation_eligible=True, classification="CONFIRMED", rejection_reason=None,
    )
    new = SimpleNamespace(
        id=2, odometer_km=Decimal("100"), received_at=T0 + timedelta(minutes=6),
        calculation_eligible=False, classification="HELD", rejection_reason=None,
    )
    state = SimpleNamespace(last_status="accepted", last_reason=None)
    with (
        patch.object(wialon_ingestion.counters_repository, "get_asset_by_wialon_id",
                     new=AsyncMock(return_value=SimpleNamespace(id="a1"))),
        patch.object(wialon_ingestion.counters_repository, "get_state_row",
                     new=AsyncMock(return_value=state)),
        patch.object(wialon_ingestion.counters_repository, "mark_conflict", new=AsyncMock()) as mark,
    ):
        result = await wialon_ingestion.ingest_wialon_reading(
            _ingest_db([old, new], new),
            unit_id="w-1", odometer_km=Decimal("100"), reading_at=T0,
            received_at=T0 + timedelta(minutes=6), transport="pull", source_time_verified=True,
        )
    mark.assert_awaited_once()
    assert result.reason == "same_time_different_odometer"
    assert state.last_reason == "same_time_different_odometer"


# ------------------------------------------------------------ release plan (pure)

def _row(i, odo, at, rx, reason="same_time_different_odometer"):
    return SimpleNamespace(
        id=i, odometer_km=Decimal(odo), reading_at=at, received_at=rx,
        rejection_reason=reason, calculation_eligible=False,
    )


def test_plan_releases_a_consistent_history():
    rows = [
        _row(1, 101, T0, T0),
        _row(2, 103, T0, T0 + timedelta(minutes=6)),
        _row(3, 110, T0 + timedelta(minutes=30), T0 + timedelta(minutes=31),
             "counter_state_blocked_by_unresolved_conflict"),
    ]
    plan = release.plan_release(rows, last_cnm=Decimal("100"), last_cnm_at=T0 - timedelta(hours=1))
    assert plan["releasable"] is True
    assert [d["representative"].id for d in plan["decisions"]] == [1, 3]


@pytest.mark.parametrize(
    "rows, problem",
    [
        ([_row(1, 105, T0, T0), _row(2, 101, T0, T0 + timedelta(minutes=6))], "same_time_value_decreased"),
        ([_row(1, 100, T0, T0), _row(2, 150, T0, T0 + timedelta(minutes=2))], "same_time_growth_too_fast"),
        ([_row(1, 100, T0, T0),
          _row(2, 90, T0 + timedelta(minutes=30), T0 + timedelta(minutes=31))], "counter_decreased"),
    ],
)
def test_plan_keeps_an_inconsistent_history_blocked(rows, problem):
    plan = release.plan_release(rows, last_cnm=Decimal("95"), last_cnm_at=T0 - timedelta(hours=1))
    assert plan["releasable"] is False and plan["problem"] == problem


def test_plan_holds_a_too_large_step_but_still_releases():
    # The live gate accepts such a step later (the state is untouched): hold, don't block.
    rows = [
        _row(1, 100, T0, T0),
        _row(2, 100000, T0 + timedelta(minutes=1), T0 + timedelta(minutes=2)),
    ]
    plan = release.plan_release(rows, last_cnm=Decimal("95"), last_cnm_at=T0 - timedelta(hours=1))
    assert plan["releasable"] is True
    assert [d["eligible"] for d in plan["decisions"]] == [True, False]
    assert "sakradi" in plan["decisions"][1]["reason"]


def test_plan_judges_history_older_than_the_state_only_by_itself():
    # State is NEWER (odometer 200) than the flagged readings (100, 101): not a decrease.
    rows = [_row(1, 100, T0, T0), _row(2, 101, T0 + timedelta(minutes=30), T0 + timedelta(minutes=31))]
    plan = release.plan_release(rows, last_cnm=Decimal("200"), last_cnm_at=T0 + timedelta(hours=2))
    assert plan["releasable"] is True and all(d["eligible"] for d in plan["decisions"])


# ------------------------------------------------------------ release (PG)

async def _seed_unit(readings):
    tag = uuid4().hex[:8]
    asset_id = uuid4()
    async with SessionFactory() as db:
        db.add(FixedAsset(
            id=asset_id, inv_number=f"REL-{tag}", asset_type="locomotive",
            status="operational", mileage=Decimal("10"), wialon_id=f"w-{tag}",
        ))
        await db.commit()
        db.add(WialonCounterState(
            asset_id=asset_id, last_status="rejected", last_reason=release.BLOCK_REASON,
            last_cnm=Decimal("95"), last_cnm_at=T0 - timedelta(hours=1),
            updated_at=T0,
        ))
        for odo, at, rx, reason in readings:
            db.add(WialonOdometerReading(
                asset_id=asset_id, source_unit_id=f"u-{tag}", odometer_km=Decimal(odo),
                reading_at=at, observed_at=at, received_at=rx, accepted=True,
                calculation_eligible=False, classification="HELD", rejection_reason=reason,
                payload_hash=uuid4().hex + uuid4().hex, payload={},
            ))
        await db.commit()
    return asset_id, f"REL-{tag}"


async def _drop_unit(asset_id):
    async with SessionFactory() as db:
        await db.execute(delete(WialonOdometerReading).where(WialonOdometerReading.asset_id == asset_id))
        await db.execute(delete(WialonCounterState).where(WialonCounterState.asset_id == asset_id))
        await db.execute(delete(AuditLog).where(AuditLog.object_id == str(asset_id)))
        await db.execute(delete(FixedAsset).where(FixedAsset.id == asset_id))
        await db.commit()


BLOCKED = "counter_state_blocked_by_unresolved_conflict"


@pytest.mark.pg
@pytest.mark.asyncio
async def test_release_dry_run_changes_nothing_and_apply_restores_a_healthy_counter():
    asset_id, inv = await _seed_unit([
        (101, T0, T0, release.BLOCK_REASON),
        (103, T0, T0 + timedelta(minutes=6), release.BLOCK_REASON),
        (110, T0 + timedelta(minutes=30), T0 + timedelta(minutes=31), BLOCKED),
    ])
    try:
        async with SessionFactory() as db:
            dry = await release.release_blocked_counters(db, actor=None, apply=False, inv_numbers=[inv])
        assert dry["summary"] == {"would_release": 1}
        async with SessionFactory() as db:
            state = await db.get(WialonCounterState, asset_id)
            assert state.last_reason == release.BLOCK_REASON
            rows = (await db.execute(select(WialonOdometerReading).where(
                WialonOdometerReading.asset_id == asset_id))).scalars().all()
            assert not any(r.calculation_eligible for r in rows)

        async with SessionFactory() as db:
            done = await release.release_blocked_counters(db, actor=None, apply=True, inv_numbers=[inv])
        assert done["summary"] == {"released": 1}
        async with SessionFactory() as db:
            state = await db.get(WialonCounterState, asset_id)
            assert state.last_reason is None
            assert state.last_cnm == Decimal("95")  # kept: the next reading catches the km up
            by_odo = {int(r.odometer_km): r for r in (await db.execute(select(WialonOdometerReading).where(
                WialonOdometerReading.asset_id == asset_id))).scalars().all()}
            assert by_odo[101].calculation_eligible and by_odo[101].rejection_reason is None
            assert by_odo[110].calculation_eligible and by_odo[110].classification == "CONFIRMED"
            assert not by_odo[103].calculation_eligible
            assert by_odo[103].rejection_reason == COUNTER_ADVANCED_REASON
            audit = (await db.execute(select(AuditLog).where(AuditLog.object_id == str(asset_id)))).scalars().all()
            events = [a for a in audit if (a.details or {}).get("event") == "counter_release"]
            assert len(events) == 1 and events[0].object_label == inv

        async with SessionFactory() as db:  # a second run finds nothing to do
            again = await release.release_blocked_counters(db, actor=None, apply=True, inv_numbers=[inv])
        assert again["summary"] == {}
    finally:
        await _drop_unit(asset_id)


@pytest.mark.pg
@pytest.mark.asyncio
async def test_release_leaves_a_contradictory_counter_blocked():
    asset_id, inv = await _seed_unit([
        (105, T0, T0, release.BLOCK_REASON),
        (101, T0, T0 + timedelta(minutes=6), release.BLOCK_REASON),  # went DOWN
    ])
    try:
        async with SessionFactory() as db:
            done = await release.release_blocked_counters(db, actor=None, apply=True, inv_numbers=[inv])
        assert done["summary"] == {"manual": 1}
        assert done["items"][0]["problem"] == "same_time_value_decreased"
        async with SessionFactory() as db:
            state = await db.get(WialonCounterState, asset_id)
            assert state.last_reason == release.BLOCK_REASON
    finally:
        await _drop_unit(asset_id)


# ------------------------------------------------------------ passport numbers

def test_numbers_that_differ_only_by_leading_zeros_are_the_same_wagon():
    assert field_changes._same_number("69", "00000069")
    assert field_changes._same_number("00013415", "13415")
    assert field_changes._same_number(" 69 ", "0069")
    assert not field_changes._same_number("4315", "4323")
    assert not field_changes._same_number("13469", "00013415")
    assert not field_changes._same_number("69A", "00000069")  # letters: not a plain number
    assert not field_changes._same_number(None, "69")
    assert field_changes._same_field_value("number", "69", "00000069")
    assert not field_changes._same_field_value("inv_number", "69", "00000069")


@pytest.mark.pg
@pytest.mark.asyncio
async def test_clean_rejects_only_leading_zero_conflicts_and_keeps_real_ones():
    tag = uuid4().hex[:6]
    actor_id, same_id, diff_id = uuid4(), uuid4(), uuid4()
    async with SessionFactory() as db:
        db.add(User(id=actor_id, email=f"a-{tag}@example.com", full_name="A",
                    **ad_user(), role="admin"))
        db.add_all([
            FixedAsset(id=same_id, inv_number=f"Z-{tag}", asset_type="wagon", status="operational", serial_number="69"),
            FixedAsset(id=diff_id, inv_number=f"D-{tag}", asset_type="wagon", status="operational", serial_number="4315"),
        ])
        await db.commit()
        db.add_all([
            AssetFieldChange(asset_id=same_id, field="number", old_value="69", new_value="00000069",
                             source="gtk", kind="conflict", status="pending"),
            AssetFieldChange(asset_id=diff_id, field="number", old_value="4315", new_value="4323",
                             source="gtk", kind="conflict", status="pending"),
        ])
        await db.commit()
    try:
        async with SessionFactory() as db:
            dry = await field_changes.reject_equivalent_number_conflicts(db, actor_id=None, apply=False)
        assert dry["would_reject_leading_zero_only"] >= 1
        async with SessionFactory() as db:
            statuses = {c.asset_id: c.status for c in (await db.execute(select(AssetFieldChange).where(
                AssetFieldChange.asset_id.in_([same_id, diff_id])))).scalars()}
            assert set(statuses.values()) == {"pending"}  # dry-run wrote nothing
        async with SessionFactory() as db:
            await field_changes.reject_equivalent_number_conflicts(db, actor_id=actor_id, apply=True)
        async with SessionFactory() as db:
            rows = {c.asset_id: c for c in (await db.execute(select(AssetFieldChange).where(
                AssetFieldChange.asset_id.in_([same_id, diff_id])))).scalars()}
            assert rows[same_id].status == "rejected" and rows[same_id].resolved_by == actor_id
            assert rows[diff_id].status == "pending"
            asset = await db.get(FixedAsset, same_id)
            assert asset.number == "69"  # passport value untouched
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(AssetFieldChange).where(AssetFieldChange.asset_id.in_([same_id, diff_id])))
            await db.execute(delete(FixedAsset).where(FixedAsset.id.in_([same_id, diff_id])))
            await db.execute(delete(User).where(User.id == actor_id))
            await db.commit()
