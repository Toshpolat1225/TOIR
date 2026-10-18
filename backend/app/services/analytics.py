import csv
import io
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User
from app.core.localization import Locale
from app.core.translation_response import localize_reference_response
from app.models.organization import Section
from app.repositories import analytics as repository


def _scope_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Master user must be assigned to a section",
    )


def _effective_section(user: User, section_id: UUID | None) -> UUID | None:
    if user.role == "master":
        if user.section_id is None:
            raise _scope_error()
        if section_id is not None and section_id != user.section_id:
            raise HTTPException(status_code=404, detail="Analytics data not found")
        return user.section_id
    return section_id


async def list_analytics(
    db: AsyncSession,
    user: User,
    *,
    view_name: str,
    section_id: UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    effective_section = _effective_section(user, section_id)
    try:
        return await repository.list_analytics(
            db,
            view_name=view_name,
            section_id=effective_section,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Analytics block not found") from exc


async def dashboard_summary(
    db: AsyncSession,
    user: User,
    *,
    section_id: UUID | None,
    section: str | None,
) -> dict[str, Any]:
    if section_id is not None and section is not None:
        raise HTTPException(
            status_code=422, detail="Use either section_id or section, not both"
        )
    if section is not None:
        if user.role == "master":
            effective_section_id = _effective_section(user, None)
        else:
            section_row = (
                await db.execute(select(Section).where(Section.name == section))
            ).scalar_one_or_none()
            if section_row is None:
                raise HTTPException(status_code=404, detail="Section not found")
            effective_section_id = section_row.id
    else:
        effective_section_id = _effective_section(user, section_id)

    assets, orders = await repository.dashboard_assets_and_orders(
        db, section_id=effective_section_id
    )
    snapshot_date = date.today()
    await repository.save_daily_readiness_snapshots(
        db,
        snapshot_date=snapshot_date,
        master_section_id=user.section_id if user.role == "master" else None,
    )

    month_start = (snapshot_date.replace(day=1) - timedelta(days=5 * 31)).replace(day=1)
    month_end = (snapshot_date.replace(day=1) + timedelta(days=monthrange(snapshot_date.year, snapshot_date.month)[1]))
    if month_end.month == 12:
        month_end = date(month_end.year + 1, 1, 1)
    else:
        month_end = date(month_end.year, month_end.month + 1, 1)
    scope_key = str(effective_section_id) if effective_section_id else "all"
    readiness_rows = await repository.monthly_readiness(
        db, month_start=month_start, month_end=month_end, scope_key=scope_key
    )
    readiness_by_month = {
        row["month"].strftime("%Y-%m"): row for row in readiness_rows
    }
    availability = []
    for offset in range(5, -1, -1):
        month_first = (snapshot_date.replace(day=1) - timedelta(days=offset * 31)).replace(day=1)
        month_key = month_first.strftime("%Y-%m")
        recorded = readiness_by_month.get(month_key)
        availability.append(
            {
                "month": month_key,
                "label": month_first.strftime("%b"),
                "pct": float(recorded["pct"]) if recorded else None,
                "days_recorded": int(recorded["days_recorded"]) if recorded else 0,
            }
        )
    return {
        "assets": assets,
        "orders": orders,
        "availability": availability,
        "availability_history_starts_at": snapshot_date.isoformat(),
    }


async def get_report(
    db: AsyncSession,
    user: User,
    *,
    report: str,
    section_id: UUID | None,
    date_from: date | None,
    date_to: date | None,
    status_filter: str | None,
    asset_type: str | None,
    q: str | None,
    limit: int,
    offset: int,
    fixed_asset_id: UUID | None = None,
    mileage_from: Decimal | None = None,
    mileage_to: Decimal | None = None,
) -> dict[str, Any]:
    if report != "work-orders" and any(value is not None for value in (fixed_asset_id, mileage_from, mileage_to)):
        raise HTTPException(status_code=422, detail="Asset and mileage filters are only available for work-order reports")
    if mileage_from is not None and mileage_to is not None and mileage_from > mileage_to:
        raise HTTPException(status_code=422, detail="mileage_from must not be greater than mileage_to")
    effective_section = _effective_section(user, section_id)
    inclusive_end = date_to + timedelta(days=1) if date_to else None
    try:
        items, total, _ = await repository.list_report_rows(
            db,
            report=report,
            section_id=effective_section,
            date_from=date_from,
            date_to=inclusive_end,
            status=status_filter,
            asset_type=asset_type,
            q=q,
            limit=limit,
            offset=offset,
            fixed_asset_id=fixed_asset_id,
            mileage_from=mileage_from,
            mileage_to=mileage_to,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Report not found") from exc
    return {"items": items, "total": total, "limit": limit, "offset": offset}


async def report_csv(
    db: AsyncSession,
    user: User,
    locale: Locale,
    *,
    report: str,
    section_id: UUID | None,
    date_from: date | None,
    date_to: date | None,
    status_filter: str | None,
    asset_type: str | None,
    q: str | None,
    fixed_asset_id: UUID | None = None,
    mileage_from: Decimal | None = None,
    mileage_to: Decimal | None = None,
) -> tuple[str, str]:
    if report != "work-orders" and any(value is not None for value in (fixed_asset_id, mileage_from, mileage_to)):
        raise HTTPException(status_code=422, detail="Asset and mileage filters are only available for work-order reports")
    if mileage_from is not None and mileage_to is not None and mileage_from > mileage_to:
        raise HTTPException(status_code=422, detail="mileage_from must not be greater than mileage_to")
    effective_section = _effective_section(user, section_id)
    inclusive_end = date_to + timedelta(days=1) if date_to else None
    try:
        rows, _, columns = await repository.list_report_rows(
            db,
            report=report,
            section_id=effective_section,
            date_from=date_from,
            date_to=inclusive_end,
            status=status_filter,
            asset_type=asset_type,
            q=q,
            limit=None,
            fixed_asset_id=fixed_asset_id,
            mileage_from=mileage_from,
            mileage_to=mileage_to,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Report not found") from exc
    report_path = f"/reports/{report}"
    rows = await localize_reference_response(
        db, path=report_path, locale=locale, payload=rows
    )
    localized_headers = _localized_report_headers(locale, columns)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(localized_headers)
    for row in rows:
        if report == "fixed-assets":
            row["asset_type"] = row.get("asset_type_label", row.get("asset_type"))
            row["status"] = row.get("asset_status_label", row.get("status"))
        elif report == "work-orders":
            row["status"] = _localized_status(locale, row.get("status"))
        elif report == "tmc-documents":
            row["status"] = _localized_tmc_status(locale, row.get("status"))
        if row.get("localized_section"):
            row["section"] = row["localized_section"]
        writer.writerow(
            [
                value.isoformat() if isinstance(value, (date, datetime)) else value
                for value in (row.get(column) for column in columns)
            ]
        )
    return "\ufeff" + output.getvalue(), report


def _localized_report_headers(locale: Locale, columns: tuple[str, ...]) -> list[str]:
    labels = {
        "ru": {
            "number": "Номер наряда", "unit": "ОС", "asset_inv_number": "Инвентарный номер",
            "section": "Участок", "work_type": "Вид работ", "status": "Статус",
            "priority": "Приоритет", "created_at": "Создан", "closed": "Закрыт",
            "mileage_at_creation": "Пробег на момент открытия, км",
            "tech": "Исполнитель", "description": "Описание", "total_cost": "Фактическая сумма",
            "total_norm_cost": "Сумма по норме", "cost_savings": "Экономия",
            "avg_deviation_percent": "Среднее отклонение, %", "id": "ID",
            "inv_number": "Инвентарный номер", "name": "Наименование", "asset_type": "Тип ОС",
            "series": "Серия", "depot": "Депо", "comm_date": "Дата ввода",
            "year_built": "Год постройки", "mileage": "Пробег", "initial_cost": "Первоначальная стоимость",
            "owner": "Владелец", "doc_no": "Номер документа", "doc_date": "Дата документа",
            "work_order_id": "ID наряда", "work_order_number": "Номер наряда", "warehouse": "Склад",
            "issued_by": "Выдал", "accepted_by": "Принял", "item_count": "Позиций ТМЦ",
            "total_quantity": "Количество ТМЦ", "total_cost": "Общая стоимость",
        },
        "uz-Latn": {
            "number": "Naryad raqami", "unit": "Asosiy vosita", "asset_inv_number": "Inventar raqami",
            "section": "Uchastka", "work_type": "Ish turi", "status": "Holat",
            "priority": "Muhimlik", "created_at": "Yaratilgan", "closed": "Yopilgan",
            "mileage_at_creation": "Ochilgan paytdagi probeg, km",
            "tech": "Ijrochi", "description": "Tavsif", "total_cost": "Amaldagi summa",
            "total_norm_cost": "Norma bo‘yicha summa", "cost_savings": "Tejamkorlik",
            "avg_deviation_percent": "O‘rtacha farq, %", "id": "ID", "inv_number": "Inventar raqami",
            "name": "Nomi", "asset_type": "Asosiy vosita turi", "series": "Seriya", "depot": "Depo",
            "comm_date": "Foydalanishga topshirilgan sana", "year_built": "Ishlab chiqarilgan yil",
            "mileage": "Probeg", "initial_cost": "Boshlang‘ich qiymat", "owner": "Egasi",
            "doc_no": "Hujjat raqami", "doc_date": "Hujjat sanasi", "work_order_id": "Naryad ID",
            "work_order_number": "Naryad raqami", "warehouse": "Ombor", "issued_by": "Bergan",
            "accepted_by": "Qabul qilgan", "item_count": "Moddiy boyliklar qatori",
            "total_quantity": "Moddiy boyliklar miqdori", "total_cost": "Umumiy qiymat",
        },
        "uz-Cyrl": {
            "number": "Наряд рақами", "unit": "Асосий восита", "asset_inv_number": "Инвентар рақами",
            "section": "Участка", "work_type": "Иш тури", "status": "Ҳолат",
            "priority": "Муҳимлик", "created_at": "Яратилган", "closed": "Ёпилган",
            "mileage_at_creation": "Очилган вақтдаги пробег, км",
            "tech": "Ижрочи", "description": "Тавсиф", "total_cost": "Амалдаги сумма",
            "total_norm_cost": "Норма бўйича сумма", "cost_savings": "Тежамкорлик",
            "avg_deviation_percent": "Ўртача фарқ, %", "id": "ID", "inv_number": "Инвентар рақами",
            "name": "Номи", "asset_type": "Асосий восита тури", "series": "Серия", "depot": "Депо",
            "comm_date": "Фойдаланишга топширилган сана", "year_built": "Ишлаб чиқарилган йил",
            "mileage": "Пробег", "initial_cost": "Бошланғич қиймат", "owner": "Эгаси",
            "doc_no": "Ҳужжат рақами", "doc_date": "Ҳужжат санаси", "work_order_id": "Наряд ID",
            "work_order_number": "Наряд рақами", "warehouse": "Омбор", "issued_by": "Берган",
            "accepted_by": "Қабул қилган", "item_count": "Моддий бойликлар қатори",
            "total_quantity": "Моддий бойликлар миқдори", "total_cost": "Умумий қиймат",
        },
    }
    return [labels[locale].get(column, column) for column in columns]


def _localized_status(locale: Locale, value: Any) -> Any:
    labels = {
        "pending": {"ru": "Ожидает", "uz-Latn": "Kutilmoqda", "uz-Cyrl": "Кутилмоқда"},
        "in_progress": {"ru": "В работе", "uz-Latn": "Bajarilmoqda", "uz-Cyrl": "Бажарилмоқда"},
        "completed": {"ru": "Выполнен", "uz-Latn": "Bajarildi", "uz-Cyrl": "Бажарилди"},
        "cancelled": {"ru": "Отменён", "uz-Latn": "Bekor qilingan", "uz-Cyrl": "Бекор қилинган"},
    }
    return labels.get(str(value), {}).get(locale, value)


def _localized_tmc_status(locale: Locale, value: Any) -> Any:
    labels = {
        "draft": {"ru": "Черновик", "uz-Latn": "Qoralama", "uz-Cyrl": "Қоралама"},
        "issued": {"ru": "Выдан", "uz-Latn": "Berildi", "uz-Cyrl": "Берилди"},
        "closed": {"ru": "Закрыт", "uz-Latn": "Yopilgan", "uz-Cyrl": "Ёпилган"},
    }
    return labels.get(str(value), {}).get(locale, value)
