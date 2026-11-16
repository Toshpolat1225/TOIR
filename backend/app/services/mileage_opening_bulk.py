"""Bulk proposal and bulk approval of wagon opening balances.

Rules (D8): maker != checker, approver is an administrator, zero/NULL and
suspicious legacy values are never approved in bulk. Both operations are
idempotent and dry-run by default.
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_source_links import AssetSourceLink
from app.core.config import settings
from app.models.assets import FixedAsset
from app.models.identity import User
from app.models.mileage import WagonMileageOpeningBalance as Opening
from app.services.audit_log import set_audit_actor
from app.services.mileage_opening import approve_opening_balance

logger = logging.getLogger(__name__)

SUSPICIOUS_KM = Decimal("1000000")
NOTE_PREFIX = "bulk-propose:"
CATEGORY_OK = "ok"
CATEGORY_ZERO = "zero_or_null"
CATEGORY_HIGH = "suspicious_high"


def categorize(mileage: Decimal | None) -> str:
    if mileage is None or mileage == 0:
        return CATEGORY_ZERO
    if mileage > SUSPICIOUS_KM:
        return CATEGORY_HIGH
    return CATEGORY_OK


async def propose_openings(
    db: AsyncSession,
    *,
    user: User,
    effective_at: datetime | None = None,
    apply: bool = False,
    asset_ids: list[UUID] | None = None,
) -> dict:
    """Propose pending opening balances from the current wagon mileage."""
    covered = exists().where(
        Opening.asset_id == FixedAsset.id,
        Opening.status.in_(("pending", "approved")),
    )
    gtk_linked = exists().where(
        AssetSourceLink.asset_id == FixedAsset.id,
        AssetSourceLink.source == "gtk",
        AssetSourceLink.status == "active",
    )
    base = select(FixedAsset).where(FixedAsset.asset_type == "wagon")
    if asset_ids is not None:
        base = base.where(FixedAsset.id.in_(asset_ids))
    total_wagons = await db.scalar(
        select(func.count()).select_from(base.subquery())
    )
    skipped_no_gtk_link = await db.scalar(
        select(func.count()).select_from(
            base.where(~covered, ~gtk_linked).subquery()
        )
    )
    candidates = list(
        (
            await db.scalars(
                base.where(~covered, gtk_linked).order_by(FixedAsset.id)
            )
        ).all()
    )
    counts = {CATEGORY_OK: 0, CATEGORY_ZERO: 0, CATEGORY_HIGH: 0}
    for asset in candidates:
        counts[categorize(asset.mileage)] += 1
    report = {
        "dry_run": not apply,
        "total_wagons": total_wagons,
        "already_covered": total_wagons - len(candidates) - skipped_no_gtk_link,
        "skipped_no_gtk_link": skipped_no_gtk_link,
        "to_propose": len(candidates),
        "zero_or_null": counts[CATEGORY_ZERO],
        "suspicious_over_1000000": counts[CATEGORY_HIGH],
        "ok": counts[CATEGORY_OK],
        "created": 0,
    }
    if not apply or not candidates:
        await db.rollback()
        return report
    proposed_at = (effective_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    set_audit_actor(
        db,
        actor_id=user.id,
        actor_name=user.full_name,
        actor_type="user",
        route="cli:wagon-opening-propose",
    )
    for asset in candidates:
        category = categorize(asset.mileage)
        db.add(
            Opening(
                asset_id=asset.id,
                mileage_km=asset.mileage or Decimal("0"),
                effective_at=proposed_at,
                created_by=user.id,
                note=f"{NOTE_PREFIX}{category}",
                status="pending",
            )
        )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise
    report["created"] = len(candidates)
    return report


async def bulk_approve_openings(
    db: AsyncSession,
    *,
    user: User,
    effective_at: datetime | None = None,
    apply: bool = False,
    asset_ids: list[UUID] | None = None,
    include_zero: bool = False,
) -> dict:
    """Approve bulk proposals in the 'ok' category. Admin only, maker != checker.

    include_zero=True also approves the zero_or_null category (the admin states
    that these wagons really start from 0 km). Suspicious values are never
    approved in bulk. effective_at defaults to the approval time: calculation
    never backfills.
    """
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can approve opening balances",
        )
    pending_statement = select(Opening).where(
        Opening.status == "pending", Opening.note.like(f"{NOTE_PREFIX}%")
    )
    if asset_ids is not None:
        pending_statement = pending_statement.where(Opening.asset_id.in_(asset_ids))
    pending = list((await db.scalars(pending_statement.order_by(Opening.id))).all())
    approved_assets = set(
        (
            await db.scalars(
                select(Opening.asset_id).where(Opening.status == "approved")
            )
        ).all()
    )
    report = {
        "dry_run": not apply,
        "pending_bulk": len(pending),
        "needs_individual_review": 0,
        "skipped_maker_is_checker": 0,
        "skipped_already_approved": 0,
        "include_zero": include_zero,
        "self_approval_allowed": settings.opening_balance_allow_self_approval,
        "eligible_zero": 0,
        "eligible": 0,
        "approved": 0,
        "failed": 0,
    }
    eligible: list[UUID] = []
    allowed_notes = {f"{NOTE_PREFIX}{CATEGORY_OK}"}
    if include_zero:
        allowed_notes.add(f"{NOTE_PREFIX}{CATEGORY_ZERO}")
    for opening in pending:
        if opening.note not in allowed_notes:
            report["needs_individual_review"] += 1
        elif (
            opening.created_by == user.id
            and not settings.opening_balance_allow_self_approval
        ):
            report["skipped_maker_is_checker"] += 1
        elif opening.asset_id in approved_assets:
            report["skipped_already_approved"] += 1
        else:
            eligible.append(opening.id)
            if opening.note == f"{NOTE_PREFIX}{CATEGORY_ZERO}":
                report["eligible_zero"] += 1
    report["eligible"] = len(eligible)
    actor_id = user.id
    await db.rollback()
    # rollback expires loaded objects; reload the actor in THIS session so that
    # reading its attributes later does not trigger an implicit (sync) lazy load.
    user = await db.get(User, actor_id)
    if not apply:
        return report
    approval_time = (effective_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    for opening_id in eligible:
        try:
            await approve_opening_balance(
                db, opening_id, user=user, effective_at=approval_time
            )
            report["approved"] += 1
        except HTTPException:
            await db.rollback()
            user = await db.get(User, actor_id)
            report["failed"] += 1
    return report
