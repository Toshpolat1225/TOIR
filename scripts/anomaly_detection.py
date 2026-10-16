#!/usr/bin/env python3
"""Analyze completed work-order item consumption using DATABASE_URL."""

import asyncio
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

CONTAMINATION = 0.1
SIGMA_THRESHOLD = 2.0
DEFAULT_UNIT_COST = 50_000
QUERY = text(
    """
    SELECT
        wo.id::text AS work_order_id,
        section.name AS section,
        work_type.code AS repair_kind,
        item.name AS item_name,
        item.unit AS item_unit,
        item.qty::double precision AS item_qty
    FROM work_orders AS wo
    JOIN sections AS section ON section.id = wo.section_id
    JOIN work_order_repairs AS repair ON repair.work_order_id = wo.id
    JOIN work_types AS work_type ON work_type.id = repair.work_type_id
    JOIN work_order_items AS item ON item.repair_id = repair.id
    WHERE wo.status = 'completed'
    ORDER BY wo.closed_at DESC NULLS LAST
    """
)


def database_url() -> URL:
    raw_url = os.environ.get("DATABASE_URL")
    if not raw_url:
        raise RuntimeError("Set DATABASE_URL in the environment before running this script.")
    parsed = make_url(raw_url)
    if parsed.get_backend_name() != "postgresql":
        raise RuntimeError("DATABASE_URL must point to PostgreSQL.")
    return parsed.set(drivername="postgresql+asyncpg")


async def load_work_order_items() -> pd.DataFrame:
    engine = create_async_engine(database_url(), pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(QUERY)
            return pd.DataFrame(result.mappings().all())
    finally:
        await engine.dispose()


def prepare_data(maintenance: pd.DataFrame) -> pd.DataFrame:
    if maintenance.empty:
        return pd.DataFrame()
    aggregates = (
        maintenance.groupby(["section", "item_name"])
        .agg(
            total_qty=("item_qty", "sum"),
            avg_qty=("item_qty", "mean"),
            std_qty=("item_qty", "std"),
            record_count=("item_qty", "count"),
            order_count=("work_order_id", "nunique"),
        )
        .reset_index()
    )
    aggregates["std_qty"] = aggregates["std_qty"].fillna(0)
    norms = (
        aggregates.groupby("item_name")
        .agg(norm_avg=("avg_qty", "mean"), norm_std=("std_qty", "mean"))
        .reset_index()
    )
    result = aggregates.merge(norms, on="item_name", how="left")
    result["deviation"] = result["avg_qty"] - result["norm_avg"]
    result["deviation_sigma"] = np.where(
        result["norm_std"] > 0, result["deviation"] / result["norm_std"], 0
    )
    result["deviation_pct"] = np.where(
        result["norm_avg"] > 0, result["deviation"] / result["norm_avg"] * 100, 0
    )
    return result


def detect_anomalies(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    frame["is_anomaly_if"] = False
    if len(frame) >= 5:
        features = frame[
            ["total_qty", "avg_qty", "deviation", "deviation_pct"]
        ].fillna(0)
        scaled = StandardScaler().fit_transform(features)
        forest = IsolationForest(
            contamination=CONTAMINATION,
            random_state=42,
            n_estimators=100,
        )
        frame["is_anomaly_if"] = forest.fit_predict(scaled) == -1
    frame["is_anomaly_sigma"] = frame["deviation_sigma"].abs() > SIGMA_THRESHOLD
    frame["estimated_loss"] = np.where(
        frame["deviation"] > 0,
        frame["deviation"] * frame["order_count"] * DEFAULT_UNIT_COST,
        0,
    )
    return frame


def report(frame: pd.DataFrame) -> None:
    anomalies = frame[
        frame["is_anomaly_if"] | frame["is_anomaly_sigma"]
    ].sort_values("estimated_loss", ascending=False)
    if anomalies.empty:
        print("Anomaliyalar topilmadi.")
        return
    print(f"Aniqlangan shubhali pozitsiyalar: {len(anomalies)}")
    for _, row in anomalies.head(20).iterrows():
        print(
            f"{row['section']} | {row['item_name']} | "
            f"o'rtacha {row['avg_qty']:.2f} (norma {row['norm_avg']:.2f}) | "
            f"og'ish {row['deviation_pct']:+.1f}% | "
            f"buyurtmalar {row['order_count']} | "
            f"taxminiy xarajat {row['estimated_loss']:,.0f} so'm"
        )
    target = Path(__file__).resolve().with_name("anomalies_report.csv")
    anomalies.to_csv(target, index=False, encoding="utf-8-sig")
    print(f"Hisobot CSV faylga yozildi: {target}")
    print(f"Tahlil vaqti: {datetime.now().strftime('%d.%m.%Y %H:%M')}")


async def run() -> None:
    maintenance = await load_work_order_items()
    if maintenance.empty:
        print("Tahlil uchun yopilgan nariyadlarda TMC sarfi topilmadi.")
        return
    report(detect_anomalies(prepare_data(maintenance)))


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except SQLAlchemyError as error:
        raise SystemExit(
            f"Database operation failed ({type(error).__name__}); details were withheld."
        ) from None
    except (ArgumentError, RuntimeError, ValueError) as error:
        raise SystemExit(str(error)) from None
