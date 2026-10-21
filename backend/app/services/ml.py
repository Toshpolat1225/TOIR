import logging
import math
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionFactory
from app.models.assets import FixedAsset
from app.models.identity import User
from app.models.work_records import AiInsight
from app.repositories import ml as repository
from app.schemas.ml import MlAnalyzeResponse, MlInsightRead

logger = logging.getLogger(__name__)
HISTORY_LIMIT = 200
MIN_ANOMALY_HISTORY = 3
MIN_MAINTENANCE_EVENTS = 3


def linear_regression_predict(values: Sequence[float]) -> float | None:
    """Fit y = a + b*x to sequential observations and predict the next value."""
    if len(values) < 2:
        return None
    x_mean = (len(values) - 1) / 2
    y_mean = sum(values) / len(values)
    denominator = sum((index - x_mean) ** 2 for index in range(len(values)))
    if denominator == 0:
        return None
    slope = sum(
        (index - x_mean) * (value - y_mean)
        for index, value in enumerate(values)
    ) / denominator
    return y_mean + slope * (len(values) - x_mean)


def linear_regression_slope(
    samples: Sequence[tuple[float, float]],
) -> float | None:
    if len(samples) < 2:
        return None
    x_mean = sum(point[0] for point in samples) / len(samples)
    y_mean = sum(point[1] for point in samples) / len(samples)
    denominator = sum((x - x_mean) ** 2 for x, _ in samples)
    if denominator <= 0:
        return None
    return sum((x - x_mean) * (y - y_mean) for x, y in samples) / denominator


def detect_consumption_anomaly(
    quantity: Decimal, historical_quantities: Sequence[Decimal]
) -> dict[str, Any] | None:
    history = list(historical_quantities[-HISTORY_LIMIT:])
    if len(history) < MIN_ANOMALY_HISTORY:
        return None
    values = [float(value) for value in history]
    actual = float(quantity)
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    standard_deviation = math.sqrt(variance)
    difference = actual - mean
    z_score = (
        abs(difference) / standard_deviation
        if standard_deviation > 0
        else (4.0 if difference else 0.0)
    )
    deviation_percent = (
        (difference / abs(mean) * 100)
        if mean != 0
        else (100.0 if difference > 0 else (-100.0 if difference < 0 else 0.0))
    )
    if z_score <= 2 and abs(deviation_percent) <= 30:
        return None
    if z_score >= 3 or abs(deviation_percent) >= 50:
        severity = "critical"
    elif z_score > 2.5 or abs(deviation_percent) >= 40:
        severity = "high"
    else:
        severity = "medium"
    return {
        "historical_count": len(history),
        "historical_mean": mean,
        "historical_stddev": standard_deviation,
        "observed_quantity": actual,
        "deviation_percent": deviation_percent,
        "z_score": z_score,
        "probability": min(z_score / 4, 1),
        "severity": severity,
    }


def predict_failure(
    maintenance_dates: Sequence[datetime],
    mileage_samples: Sequence[tuple[datetime, Decimal]],
    current_mileage: Decimal,
    *,
    today: date,
) -> dict[str, Any] | None:
    dates = sorted(maintenance_dates)
    intervals = [
        max((later - earlier).total_seconds() / 86400, 0)
        for earlier, later in zip(dates, dates[1:])
    ]
    if len(dates) < MIN_MAINTENANCE_EVENTS or len(intervals) < 2:
        return None
    predicted_interval = linear_regression_predict(intervals)
    if predicted_interval is None:
        return None
    average_interval = sum(intervals) / len(intervals)
    if average_interval <= 0:
        return None
    latest_maintenance = dates[-1]
    days_since = max(
        (datetime.combine(today, time.min, tzinfo=timezone.utc) - latest_maintenance)
        .total_seconds()
        / 86400,
        0,
    )
    failure_probability = 1 - math.exp(-days_since / average_interval)
    remaining_days = max(predicted_interval - days_since, 0)

    if mileage_samples:
        origin = mileage_samples[0][0]
        regression_samples = [
            (
                (recorded_at - origin).total_seconds() / 86400,
                float(mileage),
            )
            for recorded_at, mileage in mileage_samples
        ]
        daily_mileage = linear_regression_slope(regression_samples)
    else:
        daily_mileage = None
    predicted_failure_km = (
        float(current_mileage) + daily_mileage * remaining_days
        if daily_mileage is not None and daily_mileage > 0
        else None
    )
    remaining_km = (
        predicted_failure_km - float(current_mileage)
        if predicted_failure_km is not None
        else None
    )
    if failure_probability >= 0.7 or (
        remaining_km is not None and remaining_km < 500
    ):
        severity = "critical"
    elif failure_probability >= 0.4:
        severity = "high"
    else:
        severity = "medium"
    return {
        "probability": failure_probability,
        "severity": severity,
        "days_since_maintenance": days_since,
        "average_interval_days": average_interval,
        "predicted_interval_days": predicted_interval,
        "remaining_days": remaining_days,
        "predicted_failure_km": predicted_failure_km,
        "remaining_km": remaining_km,
        "last_maintenance_date": latest_maintenance.date().isoformat(),
    }


def calculate_health_score(
    failure_probability: float,
    anomaly_count_30_days: int,
    days_without_maintenance: float,
) -> float:
    return (
        (1 - failure_probability) * 100
        - min(anomaly_count_30_days * 5, 20)
        - min(days_without_maintenance / 30 * 5, 15)
    )


def _as_decimal(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _insight_text(severity: str, description: str) -> str:
    return f"{severity.capitalize()} ML analysis: {description}"


async def _save_anomaly(
    db: AsyncSession,
    *,
    order: Any,
    asset: FixedAsset,
    repair: dict[str, Any],
    finding: dict[str, Any],
) -> None:
    existing = await repository.get_order_insights(db, order.id, "anomaly")
    insight = next(
        (
            row
            for row in existing
            if row.details.get("work_type_id") == str(repair["work_type_id"])
        ),
        None,
    )
    details = {
        **finding,
        "work_type_id": str(repair["work_type_id"]),
        "work_type_code": repair["work_type_code"],
        "section_id": str(order.section_id),
    }
    values = {
        "asset_id": asset.id,
        "work_order_id": order.id,
        "insight_type": "anomaly",
        "probability": _as_decimal(finding["probability"]),
        "severity": finding["severity"],
        "message": _insight_text(
            finding["severity"],
            f"{repair['work_type_code']} material consumption deviates "
            f"{finding['deviation_percent']:.1f}% from section history",
        ),
        "suggested_action": "Review the work-order material quantities and supporting records.",
        "details": details,
        "is_resolved": False,
    }
    if insight is None:
        db.add(AiInsight(**values))
    else:
        for field, value in values.items():
            setattr(insight, field, value)


async def _save_prediction(
    db: AsyncSession,
    *,
    asset: FixedAsset,
    order_id: UUID | None,
    prediction: dict[str, Any],
) -> None:
    insight = await repository.get_prediction_insight(db, asset.id, order_id)
    details = {
        key: value
        for key, value in prediction.items()
        if key not in {"probability", "severity"}
    }
    values = {
        "asset_id": asset.id,
        "work_order_id": order_id,
        "insight_type": "prediction",
        "probability": _as_decimal(prediction["probability"]),
        "severity": prediction["severity"],
        "message": _insight_text(
            prediction["severity"],
            f"estimated failure risk is {prediction['probability']:.1%}",
        ),
        "suggested_action": "Review the maintenance schedule and inspect the fixed asset.",
        "details": details,
        "is_resolved": False,
    }
    if insight is None:
        db.add(AiInsight(**values))
    else:
        for field, value in values.items():
            setattr(insight, field, value)


async def _analyze_asset(
    db: AsyncSession,
    asset: FixedAsset,
    order_bundle: dict[str, Any] | None,
) -> tuple[int, int]:
    anomaly_count = 0
    order = order_bundle["order"] if order_bundle else None
    if order is not None:
        if order.closed_at is None:
            raise ValueError("A completed work order must have closed_at")
        for repair in order_bundle["repairs"]:
            history = await repository.get_anomaly_history(
                db,
                work_order_id=order.id,
                section_id=order.section_id,
                work_type_id=repair["work_type_id"],
                closed_before=order.closed_at,
            )
            finding = detect_consumption_anomaly(repair["quantity"], history)
            if finding is None:
                continue
            await _save_anomaly(
                db, order=order, asset=asset, repair=repair, finding=finding
            )
            anomaly_count += 1

    events = await repository.list_maintenance_events(db, asset)
    event_dates = [row[0] for row in events]
    if asset.last_maint_date is not None:
        asset_maintenance = datetime.combine(
            asset.last_maint_date, time.min, tzinfo=timezone.utc
        )
        if not event_dates or asset_maintenance > max(event_dates):
            event_dates.append(asset_maintenance)
    mileage_samples = await repository.list_mileage_samples(db, asset.id)
    prediction = predict_failure(
        event_dates,
        mileage_samples,
        asset.mileage,
        today=date.today(),
    )
    prediction_count = 0
    if prediction is not None:
        await db.flush()
        recent_anomalies = await repository.count_recent_anomalies(
            db,
            asset.id,
            datetime.now(timezone.utc) - timedelta(days=30),
        )
        anomaly_count_30_days = max(recent_anomalies, anomaly_count)
        health_score = calculate_health_score(
            prediction["probability"],
            anomaly_count_30_days,
            prediction["days_since_maintenance"],
        )
        asset.failure_probability = _as_decimal(prediction["probability"])
        asset.health_score = _as_decimal(health_score)
        asset.predicted_failure_km = _as_decimal(prediction["predicted_failure_km"])
        asset.last_ml_update = datetime.now(timezone.utc)
        await _save_prediction(
            db,
            asset=asset,
            order_id=order.id if order is not None else None,
            prediction=prediction,
        )
        prediction_count = 1
    return anomaly_count, prediction_count


async def analyze_fleet(db: AsyncSession) -> MlAnalyzeResponse:
    assets = await repository.list_assets_for_analysis(db)
    anomaly_count = 0
    prediction_count = 0
    for asset in assets:
        order_bundle = await repository.get_latest_completed_order(db, asset.id)
        anomalies, predictions = await _analyze_asset(db, asset, order_bundle)
        anomaly_count += anomalies
        prediction_count += predictions
    await db.commit()
    return MlAnalyzeResponse(
        analyzed_assets=len(assets),
        anomaly_insights=anomaly_count,
        prediction_insights=prediction_count,
    )


async def analyze_completed_order(order_id: UUID) -> None:
    async with SessionFactory() as db:
        bundle = await repository.get_completed_order(db, order_id)
        if bundle is None:
            raise ValueError(f"Completed work order {order_id} was not found")
        await _analyze_asset(db, bundle["asset"], bundle)
        await db.commit()
    logger.info("ML analysis finished for completed work order %s", order_id)


async def list_insights(
    db: AsyncSession,
    user: User,
    *,
    asset_id: UUID | None,
    insight_type: str | None,
    severity: str | None,
    is_resolved: bool | None,
    limit: int,
    offset: int,
) -> tuple[list[MlInsightRead], int]:
    if user.role == "master" and user.section_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Insights not found"
        )
    rows, total = await repository.list_insights(
        db,
        asset_id=asset_id,
        insight_type=insight_type,
        severity=severity,
        is_resolved=is_resolved,
        master_section_id=user.section_id if user.role == "master" else None,
        limit=limit,
        offset=offset,
    )
    items = [
        MlInsightRead(
            id=row["insight"].id,
            asset_id=row["insight"].asset_id,
            asset_name=row["asset_name"],
            work_order_id=row["insight"].work_order_id,
            work_order_number=row["work_order_number"],
            insight_type=row["insight"].insight_type,
            probability=row["insight"].probability,
            severity=row["insight"].severity,
            message=row["insight"].message,
            suggested_action=row["insight"].suggested_action,
            details=row["insight"].details,
            is_resolved=row["insight"].is_resolved,
            created_at=row["insight"].created_at,
        )
        for row in rows
    ]
    return items, total
