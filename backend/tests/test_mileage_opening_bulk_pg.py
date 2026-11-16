"""PostgreSQL tests: bulk opening-balance proposal and approval (needs pg_rehearse)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.core.database import SessionFactory
from app.models.asset_source_links import AssetSourceLink
from app.models.assets import FixedAsset
from app.models.identity import User
from app.models.mileage import WagonMileageOpeningBalance as Opening
from app.services import mileage_opening_bulk as bulk

pytestmark = [pytest.mark.pg, pytest.mark.asyncio]


async def _setup():
    maker, checker, operator = uuid4(), uuid4(), uuid4()
    wagons = {
        "ok_a": (uuid4(), Decimal("500")),
        "ok_b": (uuid4(), Decimal("1200")),
        "zero": (uuid4(), Decimal("0")),
        "high": (uuid4(), Decimal("2000000")),
        "unlinked": (uuid4(), Decimal("0")),
    }
    async with SessionFactory() as db:
        db.add_all(
            [
                User(
                    id=uid,
                    email=f"{role}-{uuid4()}@example.test",
                    full_name=role,
                    hashed_password="x",
                    role=role_name,
                )
                for uid, role, role_name in (
                    (maker, "maker", "admin"),
                    (checker, "checker", "admin"),
                    (operator, "operator", "operator"),
                )
            ]
        )
        await db.commit()
        db.add_all(
            [
                FixedAsset(
                    id=wid,
                    inv_number=f"bulk-{uuid4()}",
                    asset_type="wagon",
                    status="operational",
                    mileage=km,
                )
                for wid, km in wagons.values()
            ]
        )
        await db.commit()
        db.add_all(
            [
                AssetSourceLink(
                    asset_id=wid,
                    source="gtk",
                    external_id=str(uuid4().int % 10**9),
                    link_method="manual",
                )
                for key, (wid, _km) in wagons.items()
                if key != "unlinked"
            ]
        )
        await db.commit()
    return maker, checker, operator, wagons


async def _cleanup(users, wagons):
    ids = [w for w, _ in wagons.values()]
    async with SessionFactory() as db:
        await db.execute(delete(Opening).where(Opening.asset_id.in_(ids)))
        await db.execute(
            delete(AssetSourceLink).where(AssetSourceLink.asset_id.in_(ids))
        )
        await db.execute(delete(FixedAsset).where(FixedAsset.id.in_(ids)))
        await db.execute(delete(User).where(User.id.in_(users)))
        await db.commit()


async def _user(user_id):
    async with SessionFactory() as db:
        return await db.get(User, user_id)


async def _openings(ids):
    async with SessionFactory() as db:
        rows = (await db.scalars(select(Opening).where(Opening.asset_id.in_(ids)))).all()
    return {row.asset_id: row for row in rows}


async def test_propose_dry_run_apply_and_idempotency():
    maker, checker, operator, wagons = await _setup()
    ids = [w for w, _ in wagons.values()]
    try:
        user = await _user(maker)
        async with SessionFactory() as db:
            dry = await bulk.propose_openings(db, user=user, asset_ids=ids)
        assert dry["dry_run"] is True
        assert dry["to_propose"] == 4
        assert dry["skipped_no_gtk_link"] == 1
        assert dry["zero_or_null"] == 1
        assert dry["suspicious_over_1000000"] == 1
        assert dry["ok"] == 2
        assert await _openings(ids) == {}

        async with SessionFactory() as db:
            applied = await bulk.propose_openings(
                db, user=user, apply=True, asset_ids=ids
            )
        assert applied["created"] == 4
        rows = await _openings(ids)
        assert len(rows) == 4
        assert wagons["unlinked"][0] not in rows
        assert all(r.status == "pending" and r.created_by == maker for r in rows.values())
        assert rows[wagons["zero"][0]].note == "bulk-propose:zero_or_null"
        assert rows[wagons["high"][0]].note == "bulk-propose:suspicious_high"
        assert rows[wagons["ok_a"][0]].mileage_km == Decimal("500.00")

        async with SessionFactory() as db:
            again = await bulk.propose_openings(
                db, user=user, apply=True, asset_ids=ids
            )
        assert again["to_propose"] == 0 and again["created"] == 0
        assert len(await _openings(ids)) == 4
    finally:
        await _cleanup([maker, checker, operator], wagons)


async def test_bulk_approve_enforces_admin_maker_checker_and_skips_risky():
    maker, checker, operator, wagons = await _setup()
    ids = [w for w, _ in wagons.values()]
    try:
        maker_user = await _user(maker)
        async with SessionFactory() as db:
            await bulk.propose_openings(
                db, user=maker_user, apply=True, asset_ids=ids
            )

        # non-admin refused
        async with SessionFactory() as db:
            with pytest.raises(HTTPException) as denied:
                await bulk.bulk_approve_openings(
                    db, user=await _user(operator), apply=True, asset_ids=ids
                )
        assert denied.value.status_code == 403

        # maker cannot approve own proposals
        async with SessionFactory() as db:
            self_report = await bulk.bulk_approve_openings(
                db, user=maker_user, apply=True, asset_ids=ids
            )
        assert self_report["approved"] == 0
        assert self_report["skipped_maker_is_checker"] == 2
        assert all(r.status == "pending" for r in (await _openings(ids)).values())

        # dry-run changes nothing
        checker_user = await _user(checker)
        async with SessionFactory() as db:
            dry = await bulk.bulk_approve_openings(
                db, user=checker_user, asset_ids=ids
            )
        assert dry["dry_run"] is True and dry["eligible"] == 2
        assert all(r.status == "pending" for r in (await _openings(ids)).values())

        before = datetime.now(timezone.utc)
        async with SessionFactory() as db:
            report = await bulk.bulk_approve_openings(
                db, user=checker_user, apply=True, asset_ids=ids
            )
        assert report["approved"] == 2
        assert report["needs_individual_review"] == 2
        rows = await _openings(ids)
        for key in ("ok_a", "ok_b"):
            row = rows[wagons[key][0]]
            assert row.status == "approved"
            assert row.approved_by == checker and row.created_by == maker
            assert row.effective_at >= before - timedelta(seconds=1)  # approval time
        assert rows[wagons["zero"][0]].status == "pending"
        assert rows[wagons["high"][0]].status == "pending"

        # idempotent
        async with SessionFactory() as db:
            second = await bulk.bulk_approve_openings(
                db, user=checker_user, apply=True, asset_ids=ids
            )
        assert second["approved"] == 0 and second["eligible"] == 0
    finally:
        await _cleanup([maker, checker, operator], wagons)


async def test_explicit_effective_at_is_used_for_bulk_approval():
    maker, checker, operator, wagons = await _setup()
    ids = [w for w, _ in wagons.values()]
    chosen = datetime(2026, 11, 1, tzinfo=timezone.utc)
    try:
        async with SessionFactory() as db:
            await bulk.propose_openings(
                db, user=await _user(maker), apply=True, asset_ids=ids
            )
        async with SessionFactory() as db:
            await bulk.bulk_approve_openings(
                db,
                user=await _user(checker),
                effective_at=chosen,
                apply=True,
                asset_ids=ids,
            )
        rows = await _openings(ids)
        assert rows[wagons["ok_a"][0]].effective_at == chosen
    finally:
        await _cleanup([maker, checker, operator], wagons)


async def test_include_zero_approves_zero_but_never_suspicious_values():
    maker, checker, operator, wagons = await _setup()
    ids = [w for w, _ in wagons.values()]
    try:
        async with SessionFactory() as db:
            await bulk.propose_openings(
                db, user=await _user(maker), apply=True, asset_ids=ids
            )
        checker_user = await _user(checker)
        async with SessionFactory() as db:
            dry = await bulk.bulk_approve_openings(
                db, user=checker_user, asset_ids=ids, include_zero=True
            )
        assert dry["eligible"] == 3 and dry["eligible_zero"] == 1
        assert all(r.status == "pending" for r in (await _openings(ids)).values())
        async with SessionFactory() as db:
            report = await bulk.bulk_approve_openings(
                db, user=checker_user, apply=True, asset_ids=ids, include_zero=True
            )
        assert report["approved"] == 3
        assert report["needs_individual_review"] == 1  # suspicious_high
        rows = await _openings(ids)
        assert rows[wagons["zero"][0]].status == "approved"
        assert rows[wagons["high"][0]].status == "pending"
        # without the flag zero stays pending (default behaviour unchanged)
    finally:
        await _cleanup([maker, checker, operator], wagons)


async def test_single_superadmin_can_bulk_approve_only_with_policy_flag():
    from types import SimpleNamespace

    maker, checker, operator, wagons = await _setup()
    ids = [w for w, _ in wagons.values()]
    try:
        maker_user = await _user(maker)
        async with SessionFactory() as db:
            await bulk.propose_openings(
                db, user=maker_user, apply=True, asset_ids=ids
            )
        # flag off: blocked
        async with SessionFactory() as db:
            blocked = await bulk.bulk_approve_openings(
                db, user=maker_user, apply=True, asset_ids=ids, include_zero=True
            )
        assert blocked["approved"] == 0
        assert blocked["self_approval_allowed"] is False
        # flag on: the same admin approves, recorded in the note
        on = SimpleNamespace(opening_balance_allow_self_approval=True)
        with (
            patch.object(bulk, "settings", on),
            patch(
                "app.services.mileage_opening.settings", on
            ),
        ):
            async with SessionFactory() as db:
                report = await bulk.bulk_approve_openings(
                    db, user=maker_user, apply=True, asset_ids=ids, include_zero=True
                )
        assert report["self_approval_allowed"] is True
        assert report["approved"] == 3
        rows = await _openings(ids)
        row = rows[wagons["ok_a"][0]]
        assert row.status == "approved"
        assert row.created_by == row.approved_by == maker
        assert "[self-approved by policy]" in row.note
        assert rows[wagons["high"][0]].status == "pending"
    finally:
        await _cleanup([maker, checker, operator], wagons)


async def test_bulk_approve_works_when_actor_is_loaded_in_the_same_session():
    """Regression: rollback inside the service expired the actor (MissingGreenlet)."""
    from types import SimpleNamespace

    maker, checker, operator, wagons = await _setup()
    ids = [w for w, _ in wagons.values()]
    try:
        async with SessionFactory() as db:
            await bulk.propose_openings(
                db, user=await db.get(User, maker), apply=True, asset_ids=ids
            )
        on = SimpleNamespace(opening_balance_allow_self_approval=True)
        with (
            patch.object(bulk, "settings", on),
            patch("app.services.mileage_opening.settings", on),
        ):
            async with SessionFactory() as db:
                actor = await db.get(User, maker)  # same session as the service
                report = await bulk.bulk_approve_openings(
                    db, user=actor, apply=True, asset_ids=ids, include_zero=True
                )
        assert report["approved"] == 3 and report["failed"] == 0
    finally:
        await _cleanup([maker, checker, operator], wagons)
