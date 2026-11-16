"""Database tests for the "fix everything" batch of 2026-11-16 (need the pg_rehearse database)."""
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select, update

from app.core.config import settings
from app.core.database import SessionFactory
from app.core.security import create_refresh_token, hash_refresh_token
from app.models.assets import FixedAsset
from app.models.audit_log import AuditLog
from app.models.identity import RefreshToken, User
from app.models.mileage import WialonRawReceipt
from app.models.organization import Department, Section
from app.schemas.references import DepartmentCreate, DepartmentUpdate
from app.services import audit_log, references, wialon_health
from app.services.auth import rotate_refresh_token
from app.services.maintenance_obligations import _unobserved_days

pytestmark = [pytest.mark.pg, pytest.mark.asyncio]


async def _make_user(**extra) -> User:
    user = User(
        id=uuid4(), email=f"fx-{uuid4().hex[:8]}@example.test", full_name="FX", role="operator",
        hashed_password="x", is_active=True, **extra,
    )
    async with SessionFactory() as db:
        db.add(user)
        await db.commit()
    return user


async def _drop_user(user_id) -> None:
    async with SessionFactory() as db:
        await db.execute(delete(AuditLog).where(AuditLog.actor_user_id == user_id))
        await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


async def _add_token(user_id, *, revoked_ago: timedelta | None = None) -> str:
    raw = create_refresh_token()
    now = datetime.now(timezone.utc)
    async with SessionFactory() as db:
        db.add(
            RefreshToken(
                user_id=user_id, token_hash=hash_refresh_token(raw), expires_at=now + timedelta(days=5),
                revoked_at=None if revoked_ago is None else now - revoked_ago,
            )
        )
        await db.commit()
    return raw


# ── B6: a refresh token that comes back after it was rotated cuts every session of that user ─────────────────
async def test_reused_old_refresh_token_revokes_all_sessions_and_leaves_a_trace():
    user = await _make_user()
    try:
        old = await _add_token(user.id, revoked_ago=timedelta(minutes=10))  # rotated long ago
        live = await _add_token(user.id)  # the user's current session
        async with SessionFactory() as db:
            with pytest.raises(HTTPException) as caught:
                await rotate_refresh_token(db, old)
        assert caught.value.status_code == 401
        async with SessionFactory() as db:
            active = (
                await db.execute(select(func.count()).select_from(RefreshToken).where(
                    RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)))
            ).scalar_one()
            events = (
                await db.execute(select(AuditLog).where(AuditLog.actor_user_id == user.id, AuditLog.module == "auth"))
            ).scalars().all()
        assert active == 0, "the live session of that user must be cut too"
        assert any((event.details or {}).get("event") == "refresh_token_reuse" for event in events)
        async with SessionFactory() as db:  # and the formerly live token no longer works
            with pytest.raises(HTTPException):
                await rotate_refresh_token(db, live)
    finally:
        await _drop_user(user.id)


async def test_a_racing_second_tab_inside_the_grace_period_is_only_refused():
    user = await _make_user()
    try:
        just_rotated = await _add_token(user.id, revoked_ago=timedelta(seconds=3))
        live = await _add_token(user.id)
        async with SessionFactory() as db:
            with pytest.raises(HTTPException) as caught:
                await rotate_refresh_token(db, just_rotated)
        assert caught.value.status_code == 401
        async with SessionFactory() as db:  # the other tab's session survives
            tokens = await rotate_refresh_token(db, live)
        assert tokens.refresh_token and tokens.access_token
    finally:
        await _drop_user(user.id)


async def test_a_normal_rotation_still_works():
    user = await _make_user()
    try:
        first = await _add_token(user.id)
        async with SessionFactory() as db:
            second = (await rotate_refresh_token(db, first)).refresh_token
        async with SessionFactory() as db:
            third = (await rotate_refresh_token(db, second)).refresh_token
        assert third != second != first
    finally:
        await _drop_user(user.id)


# ── B3: department names are unique ignoring case ────────────────────────────────────────────────────────────
async def test_department_duplicate_names_are_refused_ignoring_case_and_spaces():
    tag = uuid4().hex[:8]
    created = None
    try:
        async with SessionFactory() as db:
            created = await references.create_department(db, DepartmentCreate(name=f"Участок {tag}", color="#112233"))
        async with SessionFactory() as db:
            with pytest.raises(HTTPException) as caught:
                await references.create_department(db, DepartmentCreate(name=f"  УЧАСТОК {tag.upper()}  "))
        assert caught.value.status_code == 409
        async with SessionFactory() as db:
            other = await references.create_department(db, DepartmentCreate(name=f"Другой {tag}"))
        try:
            async with SessionFactory() as db:
                with pytest.raises(HTTPException) as caught:
                    await references.update_department(db, other.id, DepartmentUpdate(name=f"участок {tag}"))
            assert caught.value.status_code == 409
            async with SessionFactory() as db:  # renaming it to itself / a free name is fine
                await references.update_department(db, other.id, DepartmentUpdate(name=f"Другой {tag}"))
        finally:
            async with SessionFactory() as db:
                await db.execute(delete(Department).where(Department.id == other.id))
                await db.commit()
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(Department).where(Department.name.ilike(f"%{tag}%")))
            await db.commit()


# ── B4: a section with people or assets cannot be archived ───────────────────────────────────────────────────
async def test_section_with_active_users_or_assets_cannot_be_archived():
    section_id, asset_id = uuid4(), uuid4()
    tag = uuid4().hex[:6]
    user = None
    try:
        async with SessionFactory() as db:
            db.add(Section(id=section_id, name=f"FX-{tag}"))
            await db.commit()
        user = await _make_user(section_id=section_id)
        async with SessionFactory() as db:
            with pytest.raises(HTTPException) as caught:
                await references.delete_section(db, section_id)
        assert caught.value.status_code == 409 and "1 active users" in caught.value.detail
        async with SessionFactory() as db:  # move the user away, then the asset blocks it
            await db.execute(update(User).where(User.id == user.id).values(section_id=None))
            db.add(FixedAsset(id=asset_id, inv_number=f"FX-{tag}", asset_type="locomotive", status="operational", section_id=section_id))
            await db.commit()
        async with SessionFactory() as db:
            with pytest.raises(HTTPException) as caught:
                await references.delete_section(db, section_id)
        assert caught.value.status_code == 409 and "1 assets" in caught.value.detail
        async with SessionFactory() as db:  # an empty section archives as before
            await db.execute(delete(FixedAsset).where(FixedAsset.id == asset_id))
            await db.commit()
        async with SessionFactory() as db:
            await references.delete_section(db, section_id)
        async with SessionFactory() as db:
            assert (await db.get(Section, section_id)).is_archived is True
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(FixedAsset).where(FixedAsset.id == asset_id))
            await db.execute(delete(AuditLog).where(AuditLog.object_id.in_([str(section_id), str(asset_id)])))
            await db.commit()
        if user is not None:
            await _drop_user(user.id)
        async with SessionFactory() as db:
            await db.execute(delete(Section).where(Section.id == section_id))
            await db.commit()


# ── B7: retention is a setting; the telemetry purge removes only feed copies ────────────────────────────────
def _audit(tag, *, actor="system", action="update", object_type="x", new_values=None, age_days=0):
    return AuditLog(
        action=action, actor_type=actor, module="wialon", route="/system/wialon-sync", object_type=object_type,
        object_label=tag, new_values=new_values, created_at=datetime.now(timezone.utc) - timedelta(days=age_days),
    )


async def test_purge_audit_telemetry_removes_feed_copies_and_keeps_business_events():
    tag = f"purge-{uuid4().hex[:8]}"
    keep = [
        _audit(tag, actor="user", object_type="wialon_raw_receipts"),  # a person wrote it: kept even on a feed table
        _audit(tag, object_type="fixed_assets", new_values={"name": "renamed", "updated_at": "x"}),  # a real change
        _audit(tag, object_type="fixed_assets", action="create", new_values={"wialon_last_sync": "x"}),  # creation
        _audit(tag, object_type="maintenance_plan", new_values={"scheduled_date": "2026-11-20"}),
        _audit(tag, object_type="wagon_mileage_opening_balances", new_values={"status": "approved"}),
    ]
    drop = [
        _audit(tag, object_type="wialon_raw_receipts", action="create"),
        _audit(tag, object_type="gtk_sync_runs", action="create"),
        _audit(tag, object_type="mileage_history", action="create"),
        _audit(tag, object_type="wialon_settings"),
        _audit(tag, object_type="fixed_assets", new_values={"wialon_last_sync": "x", "wialon_speed": 3, "updated_at": "x"}),
        _audit(tag, object_type="fixed_assets", new_values={"mileage": 5, "updated_at": "x"}),
    ]
    async with SessionFactory() as db:
        db.add_all(keep + drop)
        await db.commit()
    try:
        dry = await audit_log.purge_audit_telemetry(apply=False)
        assert dry["applied"] is False and dry["deleted"] == 0 and dry["telemetry_rows"] >= len(drop)
        async with SessionFactory() as db:
            assert (await db.execute(select(func.count()).select_from(AuditLog).where(AuditLog.object_label == tag))).scalar_one() == len(keep) + len(drop)
        applied = await audit_log.purge_audit_telemetry(apply=True, batch_size=2)  # several batches
        assert applied["deleted"] >= len(drop)
        async with SessionFactory() as db:
            left = (await db.execute(select(AuditLog).where(AuditLog.object_label == tag))).scalars().all()
        assert len(left) == len(keep)
        assert {row.object_type for row in left} == {"wialon_raw_receipts", "fixed_assets", "maintenance_plan", "wagon_mileage_opening_balances"}
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(AuditLog).where(AuditLog.object_label == tag))
            await db.commit()


async def test_audit_retention_follows_the_setting(monkeypatch):
    tag = f"ret-{uuid4().hex[:8]}"
    async with SessionFactory() as db:
        db.add_all([_audit(tag, actor="user", object_type="users", age_days=100), _audit(tag, actor="user", object_type="users", age_days=5)])
        await db.commit()
    try:
        monkeypatch.setattr(settings, "audit_retention_days", 365)
        await audit_log.delete_expired_audit_logs()
        async with SessionFactory() as db:
            assert (await db.execute(select(func.count()).select_from(AuditLog).where(AuditLog.object_label == tag))).scalar_one() == 2
        monkeypatch.setattr(settings, "audit_retention_days", 30)
        await audit_log.delete_expired_audit_logs()
        async with SessionFactory() as db:
            assert (await db.execute(select(func.count()).select_from(AuditLog).where(AuditLog.object_label == tag))).scalar_one() == 1
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(AuditLog).where(AuditLog.object_label == tag))
            await db.commit()


# ── B11: which days did our collector really watch? ──────────────────────────────────────────────────────────
async def test_unobserved_days_are_days_with_too_few_collector_hours():
    base = datetime(2020, 3, 10, tzinfo=timezone.utc)
    marker = f"fx-{uuid4().hex[:8]}"
    rows = []
    for hour in range(0, 16):  # 2020-03-10: 16 distinct hours -> observed
        rows.append(base + timedelta(hours=hour))
    for hour in (3, 4):  # 2020-03-11: 2 hours -> unobserved
        rows.append(base + timedelta(days=1, hours=hour))
    # 2020-03-12: nothing at all -> unobserved; 2020-03-13: 14 hours -> observed
    for hour in range(0, 14):
        rows.append(base + timedelta(days=3, hours=hour))
    async with SessionFactory() as db:
        db.add_all(
            [
                WialonRawReceipt(source_unit_id=marker, transport="pull", received_at=moment, payload_hash=uuid4().hex + uuid4().hex, payload={})
                for moment in rows
            ]
        )
        await db.commit()
    try:
        async with SessionFactory() as db:
            result = await _unobserved_days(db, date(2020, 3, 9), date(2020, 3, 13))
        # the table may hold other receipts later in time; only the window above matters here
        assert date(2020, 3, 11) in result and date(2020, 3, 12) in result
        assert date(2020, 3, 10) not in result and date(2020, 3, 13) not in result
        assert date(2020, 3, 9) not in result  # before the first receipt we ever got: not flagged
    finally:
        async with SessionFactory() as db:
            await db.execute(delete(WialonRawReceipt).where(WialonRawReceipt.source_unit_id == marker))
            await db.commit()


# ── B10: the Wialon health report is read-only and runs on an empty/any database ────────────────────────────
async def test_wialon_health_report_runs_and_has_the_expected_sections():
    async with SessionFactory() as db:
        report = await wialon_health.build_report(db, silent_hours=24, reject_days=7)
    assert set(report) == {"silent", "unmatched_units", "suspect_counters", "rejected_readings"}
    assert report["silent"]["hours"] == 24 and report["rejected_readings"]["days"] == 7
    assert isinstance(report["rejected_readings"]["units"], list)
