import argparse
import asyncio
import csv
import getpass
import json
import logging
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionFactory, engine
from app.integrations.wialon_client import (
    WialonClient,
    WialonClientError,
    diagnostic_counter,
    item_field_names,
    parse_units,
)
from app.models.assets import FixedAsset
from app.models.maintenance import MaintenanceInterval, WorkType
from app.models.organization import Department, Section
from app.services.auth import create_first_ad_admin, issue_emergency_session
from app.services import maintenance as maintenance_service
from app.models.identity import User
from app.services import mileage_opening_bulk, wagon_mileage_report
from app.services.wagon_mileage_run import run_wagon_mileage

logger = logging.getLogger(__name__)

REFERENCE_DEPARTMENTS = (
    ("Участок ПТОВ", "#0ea5e9", "ПТОВ"),
    ("Участок ПТОЛ", "#3b82f6", "ПТОЛ"),
    ("Участок ВРП", "#22c55e", "ВРП"),
    ("Электровозное депо", "#8b5cf6", "ЭЛ_ДЕПО"),
)
REFERENCE_WORK_TYPES = (
    ("ТО-1", "locomotive"),
    ("ТО-2", "locomotive"),
    ("ТО-3", "locomotive"),
    ("ТР-1", "locomotive"),
    ("ТР-2", "locomotive"),
    ("ТР-3", "locomotive"),
    ("СР", "locomotive"),
    ("КР", "locomotive"),
    ("ВНП", "locomotive"),
    ("ТО-1В", "wagon"),
    ("ТО-2В", "wagon"),
    ("ТОР", "wagon"),
    ("ТОВ", "wagon"),
    ("ДР", "wagon"),
    ("КРВ", "wagon"),
    ("ВНВ", "wagon"),
)
MAINTENANCE_INTERVALS = (
    ("ТО-1", Decimal("5000")),
    ("ТО-2", Decimal("15000")),
    ("ТО-3", Decimal("30000")),
    ("ТР-1", Decimal("100000")),
    ("ТР-2", Decimal("200000")),
    ("ТР-3", Decimal("400000")),
    ("СР", Decimal("800000")),
    ("КР", Decimal("1600000")),
)


async def _create_ad_admin(email: str, ad_username: str, full_name: str) -> int:
    try:
        async with SessionFactory() as db:
            user_id = await create_first_ad_admin(db, email, ad_username, full_name)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except IntegrityError:
        print("Could not create admin; the email or login may already be registered.", file=sys.stderr)
        return 2
    except SQLAlchemyError:
        print("Database operation failed; verify the database connection and schema.", file=sys.stderr)
        return 2
    finally:
        await engine.dispose()
    print(f"Admin user created successfully (id: {user_id}). Sign in with the domain password.")
    return 0


async def _emergency_session(admin: str) -> int:
    """Server-shell only: 15 minutes for an active directory administrator when the domain is down (audited)."""
    import socket

    operator = f"{getpass.getuser()}@{socket.gethostname()}"
    try:
        async with SessionFactory() as db:
            token = await issue_emergency_session(db, admin, operator=operator)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except SQLAlchemyError:
        print("Database operation failed; verify the database connection and schema.", file=sys.stderr)
        return 2
    finally:
        await engine.dispose()
    print("Emergency session started (15 minutes, audited). It cannot be extended.")
    print("In the browser, open the TOIR site, press F12, Console, and run:")
    print(f"  cookieStore.set({{name: 'toir_refresh_token', value: '{token}', path: '{settings.refresh_cookie_path}'}}).then(() => location.reload())")
    print("The token is shown once. Do not share it; it is not stored anywhere in plain text.")
    return 0


async def _seed_reference() -> int:
    department_count = 0
    section_count = 0
    work_type_count = 0
    try:
        async with SessionFactory() as db:
            for department_name, color, section_name in REFERENCE_DEPARTMENTS:
                result = await db.execute(
                    select(Department).where(Department.name == department_name)
                )
                department = result.scalar_one_or_none()
                if department is None:
                    department = Department(name=department_name, color=color)
                    db.add(department)
                    await db.flush()
                    department_count += 1

                result = await db.execute(
                    select(Section).where(
                        Section.name == section_name,
                        Section.department_id == department.id,
                        Section.parent_id.is_(None),
                        Section.unit_type == "section",
                        Section.is_archived.is_(False),
                    )
                )
                matching_sections = result.scalars().all()
                if len(matching_sections) > 1:
                    print(
                        f"Reference section name is ambiguous in department {department_name!r}: "
                        f"{section_name!r}. Resolve the duplicate before seeding.",
                        file=sys.stderr,
                    )
                    return 2
                if not matching_sections:
                    db.add(
                        Section(
                            name=section_name,
                            department_id=department.id,
                        )
                    )
                    section_count += 1

            for sort_order, (code, unit_type) in enumerate(REFERENCE_WORK_TYPES, start=1):
                result = await db.execute(
                    select(WorkType).where(WorkType.code == code)
                )
                if result.scalar_one_or_none() is None:
                    db.add(
                        WorkType(
                            code=code,
                            name=code,
                            unit_type=unit_type,
                            sort_order=sort_order,
                        )
                    )
                    work_type_count += 1

            await db.commit()
    except IntegrityError:
        print(
            "Reference data could not be seeded because a unique or foreign-key constraint failed.",
            file=sys.stderr,
        )
        return 2
    except SQLAlchemyError:
        print(
            "Database operation failed; verify the database connection and schema.",
            file=sys.stderr,
        )
        return 2
    finally:
        await engine.dispose()

    print(
        "Reference data ready "
        f"(departments added: {department_count}, sections added: {section_count}, "
        f"work types added: {work_type_count}; maintenance intervals unchanged)."
    )
    return 0


async def _seed_intervals() -> int:
    created = 0
    updated = 0
    interval_codes = [code for code, _ in MAINTENANCE_INTERVALS]
    try:
        async with SessionFactory() as db:
            work_types = (
                await db.execute(
                    select(WorkType.code, WorkType.id).where(
                        WorkType.code.in_(interval_codes)
                    )
                )
            ).all()
            work_type_ids = {code: work_type_id for code, work_type_id in work_types}
            for code, interval_km in MAINTENANCE_INTERVALS:
                result = await db.execute(
                    select(MaintenanceInterval).where(
                        MaintenanceInterval.code == code
                    )
                )
                interval = result.scalar_one_or_none()
                if interval is None:
                    interval = MaintenanceInterval(code=code, name=code)
                    db.add(interval)
                    created += 1
                else:
                    updated += 1
                interval.name = code
                interval.interval_km = interval_km
                interval.interval_days = None
                interval.asset_types = ["locomotive", "diesel"]
                interval.warn_percent = Decimal("10")
                interval.is_active = True
                interval.work_type_id = work_type_ids.get(code)
                interval.updated_at = datetime.now(timezone.utc)
            await db.commit()
    except IntegrityError:
        print(
            "Maintenance intervals could not be seeded because a reference constraint failed.",
            file=sys.stderr,
        )
        return 2
    except SQLAlchemyError:
        print(
            "Database operation failed; verify the database connection and schema.",
            file=sys.stderr,
        )
        return 2
    finally:
        await engine.dispose()

    print(
        "Maintenance intervals ready "
        f"(added: {created}, updated: {updated}; work types linked by code)."
    )
    return 0


async def _recalculate_asset_plans(
    db: AsyncSession, assets: list[FixedAsset]
) -> tuple[int, int]:
    created = 0
    errors = 0
    for asset in assets:
        try:
            async with db.begin_nested():
                asset_created = await maintenance_service.reconcile_asset_plans(
                    db, asset, asset.mileage
                )
            await db.commit()
            created += asset_created
        except Exception:
            await db.rollback()
            errors += 1
            logger.exception(
                "Could not recalculate maintenance plans for asset %s", asset.id
            )
    return created, errors


async def _recalculate_plans() -> int:
    try:
        async with SessionFactory() as db:
            result = await db.execute(
                select(FixedAsset)
                .where(
                    FixedAsset.asset_type.in_(("locomotive", "diesel")),
                    FixedAsset.status == "operational",
                )
                .order_by(FixedAsset.id)
            )
            assets = list(result.scalars().all())
            created, errors = await _recalculate_asset_plans(db, assets)
    except SQLAlchemyError:
        logger.exception("Could not load assets for maintenance plan recalculation")
        return 2
    finally:
        await engine.dispose()

    print(
        "Rejalashtirish yakunlandi: "
        f"ko‘rib chiqildi: {len(assets)}; yangi rejalar: {created}; xatolar: {errors}."
    )
    return 1 if errors else 0


async def _wagon_mileage_run(*, dry_run: bool) -> int:
    if not dry_run and not settings.wagon_mileage_engine_enabled:
        print(
            "Rad etildi: real ishga tushirish uchun WAGON_MILEAGE_ENGINE_ENABLED=true "
            "kerak. --dry-run har doim ruxsat etiladi.",
            file=sys.stderr,
        )
        return 3
    try:
        async with SessionFactory() as db:
            report = await run_wagon_mileage(db, dry_run=dry_run)
    except SQLAlchemyError as exc:
        logger.error("Wagon mileage calculation failed (%s)", type(exc).__name__)
        return 2
    finally:
        await engine.dispose()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


async def _wagon_mileage_report(csv_path: str | None) -> int:
    from pathlib import Path

    try:
        async with SessionFactory() as db:
            report = await wagon_mileage_report.build_report(db)
            await db.rollback()
    except SQLAlchemyError as exc:
        logger.error("Wagon mileage report failed (%s)", type(exc).__name__)
        return 2
    finally:
        await engine.dispose()
    rows = report.pop("rows")
    if csv_path:
        wagon_mileage_report.write_csv(rows, Path(csv_path))
        report["csv"] = csv_path
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _parse_effective_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--effective-at must include a timezone, e.g. 2026-11-13T00:00:00+05:00")
    return parsed


async def _wagon_opening_bulk(
    *,
    mode: str,
    actor_email: str,
    effective_at: str | None,
    apply: bool,
    include_zero: bool = False,
) -> int:
    try:
        effective = _parse_effective_at(effective_at)
        async with SessionFactory() as db:
            user = await db.scalar(select(User).where(User.email == actor_email))
            if user is None:
                print("Foydalanuvchi topilmadi (--actor-email).", file=sys.stderr)
                return 2
            if mode == "propose":
                report = await mileage_opening_bulk.propose_openings(
                    db, user=user, effective_at=effective, apply=apply
                )
            else:
                report = await mileage_opening_bulk.bulk_approve_openings(
                    db,
                    user=user,
                    effective_at=effective,
                    apply=apply,
                    include_zero=include_zero,
                )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        detail = getattr(exc, "detail", None) or type(exc).__name__
        print(f"Bajarilmadi: {detail}", file=sys.stderr)
        return 2
    finally:
        await engine.dispose()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0



async def _actor_for_cli(db: AsyncSession, actor_email: str | None, apply: bool) -> User | None:
    if actor_email is None:
        if apply:
            raise ValueError("--actor-email majburiy (--apply bilan)")
        return None
    user = await db.scalar(select(User).where(User.email == actor_email.strip()))
    if user is None:
        raise ValueError("Foydalanuvchi topilmadi (--actor-email).")
    return user


async def _wialon_counter_release(
    actor_email: str | None, apply: bool, inv_numbers: list[str] | None
) -> int:
    from app.services import wialon_counter_release

    try:
        async with SessionFactory() as db:
            actor = await _actor_for_cli(db, actor_email, apply)
            report = await wialon_counter_release.release_blocked_counters(
                db, actor=actor, apply=apply, inv_numbers=inv_numbers
            )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        detail = getattr(exc, "detail", None) or type(exc).__name__
        print(f"Bajarilmadi: {detail}", file=sys.stderr)
        return 2
    finally:
        await engine.dispose()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


async def _asset_conflicts_clean(actor_email: str | None, apply: bool) -> int:
    from app.services import asset_field_changes as field_changes_service

    try:
        async with SessionFactory() as db:
            actor = await _actor_for_cli(db, actor_email, apply)
            report = await field_changes_service.reject_equivalent_number_conflicts(
                db, actor_id=actor.id if actor else None, apply=apply
            )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        detail = getattr(exc, "detail", None) or type(exc).__name__
        print(f"Bajarilmadi: {detail}", file=sys.stderr)
        return 2
    finally:
        await engine.dispose()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _probe_unit(item: dict[str, object]) -> dict[str, object]:
    item_copy = dict(item)
    item_copy.setdefault("id", "__probe__")
    if not item_copy.get("nm") and not item_copy.get("name"):
        item_copy["nm"] = "__probe__"
    parsed_units = parse_units({"items": [item_copy]})
    parsed = parsed_units[0] if parsed_units else None

    mileage_field, mileage = diagnostic_counter(item, counter="mileage")
    engine_hours_field, engine_hours = diagnostic_counter(
        item, counter="engine_hours"
    )
    measurement_system = item.get("mu")
    try:
        measurement_system_code = int(measurement_system)
    except (TypeError, ValueError):
        measurement_system_code = None

    estimated_km: Decimal | None = None
    if mileage is not None and measurement_system_code in {0, 3}:
        estimated_km = mileage
        mileage_assumption = (
            f"mu={measurement_system_code}: xom hisoblagich km deb faraz qilindi"
        )
    elif mileage is not None and measurement_system_code in {1, 2}:
        estimated_km = mileage * Decimal("1.609344")
        mileage_assumption = (
            f"mu={measurement_system_code}: xom hisoblagich mil deb faraz qilinib, "
            "km ga aylantirildi"
        )
    else:
        mileage_assumption = (
            "o‘lchov birligi aniqlanmadi; Wialon hisoblagich sozlamasida tasdiqlang"
        )

    position = item.get("pos")
    message = item.get("lmsg")
    if not isinstance(position, dict) and isinstance(message, dict):
        position = message.get("pos")
    position_present = isinstance(position, dict) and (
        "x" in position or "y" in position
    )

    return {
        "id": item.get("id"),
        "name": item.get("nm") or item.get("name"),
        "field_names": item_field_names(item),
        "mileage": {
            "field": mileage_field,
            "raw": str(mileage) if mileage is not None else None,
            "estimated_km": str(estimated_km) if estimated_km is not None else None,
            "assumption": mileage_assumption,
        },
        "engine_hours": {
            "field": engine_hours_field,
            "raw": str(engine_hours) if engine_hours is not None else None,
        },
        "speed": str(parsed.speed) if parsed and parsed.speed is not None else None,
        "last_message_at_utc": (
            parsed.last_message_at.isoformat()
            if parsed and parsed.last_message_at is not None
            else None
        ),
        "position_present": position_present,
    }


async def _maintenance_shadow_report() -> int:
    from app.services import maintenance_lifecycle

    try:
        async with SessionFactory() as db:
            report = await maintenance_lifecycle.shadow_report(db)
    except SQLAlchemyError:
        logger.exception("Could not build the maintenance shadow report")
        return 2
    finally:
        await engine.dispose()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


async def _maintenance_health(fix: bool) -> int:
    from app.services import maintenance_lifecycle

    try:
        async with SessionFactory() as db:
            report = await maintenance_lifecycle.run_health(db, fix=fix)
            if fix:
                await db.commit()
    except SQLAlchemyError:
        logger.exception("Could not run the maintenance health check")
        return 2
    finally:
        await engine.dispose()
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if report.ok or fix else 1


async def _maintenance_baseline_import(path: str, apply: bool) -> int:
    from app.services import maintenance_lifecycle

    try:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:
        print(f"Fayl o'qilmadi: {exc}", file=sys.stderr)
        return 2
    try:
        async with SessionFactory() as db:
            report = await maintenance_lifecycle.import_baselines(db, rows, apply=apply)
    except SQLAlchemyError:
        logger.exception("Could not import maintenance baselines")
        return 2
    finally:
        await engine.dispose()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if not apply:
        print("DRY-RUN: hech narsa yozilmadi. Yozish uchun --apply qo'shing.", file=sys.stderr)
    return 0 if not report["errors"] else 1


async def _audit_purge_telemetry(apply: bool, batch_size: int) -> int:
    from app.services import audit_log

    try:
        report = await audit_log.purge_audit_telemetry(apply=apply, batch_size=batch_size)
    except SQLAlchemyError:
        logger.exception("Could not purge audit telemetry")
        return 2
    finally:
        await engine.dispose()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if not apply:
        print("DRY-RUN: hech narsa o'chirilmadi. O'chirish uchun --apply qo'shing.", file=sys.stderr)
    return 0


async def _wagon_ledger_purge(older_than_days: int, apply: bool) -> int:
    from app.services import wagon_ledger_retention

    try:
        report = await wagon_ledger_retention.purge_superseded(older_than_days=older_than_days, apply=apply)
    except (ValueError, SQLAlchemyError) as exc:
        print(f"Bajarilmadi: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        await engine.dispose()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if not apply:
        print("DRY-RUN: hech narsa o'chirilmadi. O'chirish uchun --apply qo'shing (avval dump oling).", file=sys.stderr)
    return 0


async def _data_migration_import(
    path: str | None, name: str | None, source_file: str | None, field: str, record_only: bool, apply: bool, manifest: str | None = None
) -> int:
    from app.services import data_migration_import

    try:
        if manifest:
            jobs = data_migration_import.load_manifest(manifest)
        elif path and name and source_file:
            jobs = [{"file": path, "name": name, "source_file": source_file, "field": field}]
        else:
            print("--manifest yoki (--file, --name, --source-file) kerak", file=sys.stderr)
            return 2
    except (OSError, ValueError) as exc:
        print(f"Manifest o'qilmadi: {exc}", file=sys.stderr)
        return 2
    reports = []
    try:
        for job in jobs:
            with open(job["file"], newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            async with SessionFactory() as db:
                report = await data_migration_import.import_rows(
                    db, rows, batch_name=job["name"], source_file=job["source_file"], field=job["field"], record_only=record_only, commit=apply
                )
            reports.append({"batch": job["name"], **report})
    except (OSError, ValueError, SQLAlchemyError) as exc:
        print(f"Bajarilmadi: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        await engine.dispose()
    report = reports[0] if len(reports) == 1 and not manifest else reports
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if not apply:
        print("DRY-RUN: hech narsa yozilmadi. Yozish uchun --apply qo'shing (avval dump oling).", file=sys.stderr)
    return 0


async def _demo_seed(reset: bool = False) -> int:
    from app.services import demo_seed

    try:
        async with SessionFactory() as db:
            if reset:
                print(json.dumps({"removed": await demo_seed.reset(db)}, ensure_ascii=False, indent=2))
            counts = None
            for attempt in range(1, 5):  # the background GTK/Wialon sync can deadlock with the seed: the seed is one transaction, so it is safe to retry
                try:
                    counts = await demo_seed.seed(db)
                    break
                except DBAPIError as exc:
                    if "deadlock" not in str(exc).lower() or attempt == 4:
                        raise
                    await db.rollback()
                    print(f"deadlock, retry {attempt}", file=sys.stderr)
    except (ValueError, SQLAlchemyError) as exc:
        print(f"Bajarilmadi: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        await engine.dispose()
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    return 0


async def _stock_import(path: str, apply: bool, as_of: str | None, kind: str | None) -> int:
    from datetime import date as _date

    from app.services import stock_import

    try:
        with open(path, "rb") as handle:
            content = handle.read()
        async with SessionFactory() as db:
            report = await stock_import.import_file(
                db, content, os.path.basename(path), apply=apply, as_of=_date.fromisoformat(as_of) if as_of else None, kind=kind
            )
    except (OSError, ValueError, SQLAlchemyError) as exc:
        print(f"Bajarilmadi: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        await engine.dispose()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if not apply:
        print("DRY-RUN: hech narsa yozilmadi. Yozish uchun --apply qo'shing.", file=sys.stderr)
    return 0


async def _repair_norms_import(manifest: str, apply: bool) -> int:
    from app.services import repair_norms

    try:
        jobs = repair_norms.load_manifest(manifest)
    except (OSError, ValueError) as exc:
        print(f"Manifest o'qilmadi: {exc}", file=sys.stderr)
        return 2
    reports = []
    try:
        for job in jobs:
            with open(job["file"], newline="", encoding="utf-8-sig") as handle:
                rows = list(csv.DictReader(handle))
            async with SessionFactory() as db:
                report = await repair_norms.import_set(
                    db, rows, work_type_code=job["work_type_code"], asset_type=job["asset_type"], model_name=job["model_name"] or None,
                    source_file=job["source_file"], source_sheet=job["source_sheet"], commit=apply,
                    norm_group=job["norm_group"], basis=job["basis"],
                )
            reports.append(report)
    except (OSError, ValueError, SQLAlchemyError) as exc:
        print(f"Bajarilmadi: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        await engine.dispose()
    print(json.dumps(reports, ensure_ascii=False, indent=2, default=str))
    if not apply:
        print("DRY-RUN: hech narsa yozilmadi. Yozish uchun --apply qo'shing (avval dump oling).", file=sys.stderr)
    return 0


async def _wialon_health_report(silent_hours: int, reject_days: int) -> int:
    from app.services import wialon_health

    try:
        async with SessionFactory() as db:
            report = await wialon_health.build_report(db, silent_hours=silent_hours, reject_days=reject_days)
    except SQLAlchemyError:
        logger.exception("Could not build the Wialon health report")
        return 2
    finally:
        await engine.dispose()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


async def _wialon_probe() -> int:
    if settings.wialon_host is None or settings.wialon_token is None:
        print("Wialon sozlanmagan: WIALON_HOST yoki WIALON_TOKEN yo‘q.", file=sys.stderr)
        return 2

    try:
        client = WialonClient(
            settings.wialon_host,
            settings.wialon_token.get_secret_value(),
        )
        items = await client.fetch_diagnostic_items()
    except WialonClientError as exc:
        print(exc.status_message, file=sys.stderr)
        return 1
    finally:
        await engine.dispose()

    report = {
        "unit_count": len(items),
        "shown_count": min(len(items), 20),
        "truncated": len(items) > 20,
        "units": [_probe_unit(item) for item in items[:20]],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


async def _wialon_track_backfill(days: int) -> int:
    from app.services import position_history

    if settings.wialon_host is None or settings.wialon_token is None:
        print("Wialon is not configured", file=sys.stderr)
        return 2
    client = WialonClient(settings.wialon_host, settings.wialon_token.get_secret_value())
    try:
        async with SessionFactory() as session:
            stats = await position_history.backfill_wialon_tracks(
                session, client, days=max(1, min(days, 60)),
                progress=lambda unit, raw, kept: print(f"unit {unit}: {raw} messages -> {kept} stored points", flush=True),
            )
        print(json.dumps(stats))
        return 0
    except WialonClientError as exc:
        print(f"Wialon error: {exc}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()


async def _gtk_gps_backfill(days: int) -> int:
    from app.services import gtk_gps

    if not settings.gtk_credentials_configured:
        print("GTK is not configured", file=sys.stderr)
        return 2
    try:
        async with SessionFactory() as session:
            run = await gtk_gps.sync_gtk_gps(session, backfill_days=max(1, min(days, 120)), progress=lambda line: print(line, flush=True))
        print(json.dumps({"status": run.status, "units": run.units, "tracks_ok": run.tracks_ok, "tracks_failed": run.tracks_failed, "points": run.points_stored}))
        return 0 if run.status != "failed" else 1
    finally:
        await engine.dispose()


async def _gps_analytics(days: int, wagons: bool, diff: bool) -> int:
    from app.services import gps_assessment, wagon_gps

    try:
        async with SessionFactory() as session:
            if diff:
                print(json.dumps(await wagon_gps.diff_against_ledger(session, days), ensure_ascii=False, default=str))
                return 0
            n = await gps_assessment.assess_range(session, max(1, min(days, 90)))
            print(json.dumps({"day_assessments": n}), flush=True)
        if wagons:
            async with SessionFactory() as session:
                m = await wagon_gps.compute_segments(session, back_days=max(1, min(days, 60)), progress=lambda line: print(line, flush=True))
                print(json.dumps({"wagon_segments": m}))
        return 0
    finally:
        await engine.dispose()


async def _scales_rematch() -> int:
    from app.services import scales as scales_service

    try:
        async with SessionFactory() as session:
            count = await scales_service.rematch_all(session)
        print(json.dumps({"rematched": count}))
        return 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    admin_parser = subparsers.add_parser("create-ad-admin", help="Create the first administrator as a directory (AD) account; no password")
    admin_parser.add_argument("--email", required=True)
    admin_parser.add_argument("--ad-username", required=True)
    admin_parser.add_argument("--full-name", required=True)
    emergency_parser = subparsers.add_parser("emergency-session", help="15-minute audited session for an active directory administrator when the domain is down (server shell only)")
    emergency_parser.add_argument("--admin", required=True, help="Administrator email or directory login")
    subparsers.add_parser("seed-reference", help="Create initial directory reference data")
    subparsers.add_parser("seed-intervals", help="Idempotently seed maintenance intervals")
    subparsers.add_parser(
        "recalculate-plans",
        help="Idempotently recalculate plans for operational locomotive and diesel assets",
    )
    subparsers.add_parser("wialon-probe", help="Read safe Wialon unit diagnostics")
    track_parser = subparsers.add_parser(
        "wialon-track-backfill",
        help="Load the past GPS track of every linked Wialon unit into the position history (idempotent; a day at a time, thinned)",
    )
    track_parser.add_argument("--days", type=int, default=7)
    gtk_gps_parser = subparsers.add_parser(
        "gtk-gps-backfill",
        help="Fetch GTK's own GPS tracks for the last N local days of every linked locomotive (read-only towards GTK)",
    )
    gtk_gps_parser.add_argument("--days", type=int, default=30)
    gps_an_parser = subparsers.add_parser(
        "gps-analytics",
        help="Recompute the per-day GPS assessments (and with --wagons the wagon segments) for the last N days; --diff compares wagon segments with the mileage ledger (read-only)",
    )
    gps_an_parser.add_argument("--days", type=int, default=31)
    gps_an_parser.add_argument("--wagons", action="store_true")
    gps_an_parser.add_argument("--diff", action="store_true")
    subparsers.add_parser(
        "scales-rematch",
        help="Recompute every derived weighing-scale column from the raw rows, GTK history and corrections (idempotent)",
    )
    subparsers.add_parser(
        "maintenance-shadow-report",
        help="Read-only: what the living-plan engine sees (states, confidence, pace, what it would plan)",
    )
    wialon_health_parser = subparsers.add_parser(
        "wialon-health-report",
        help="Read-only: silent units, unlinked units, suspect counters and repeatedly rejected readings",
    )
    wialon_health_parser.add_argument("--silent-hours", type=int, default=24)
    wialon_health_parser.add_argument("--reject-days", type=int, default=7)
    purge_parser = subparsers.add_parser(
        "audit-purge-telemetry",
        help="Delete audit rows that only mirror automatic Wialon/GTK feeds (dry-run by default; take a dump first)",
    )
    purge_parser.add_argument("--apply", action="store_true")
    purge_parser.add_argument("--batch-size", type=int, default=50_000)
    migration_parser = subparsers.add_parser(
        "data-migration-import",
        help="Import a CSV (inv,[serial,]date[,raw]) into assets and the migration journal (dry-run by default; take a dump first)",
    )
    migration_parser.add_argument("--file")
    migration_parser.add_argument("--name", help="Batch name shown on the Migration page")
    migration_parser.add_argument("--source-file", help="Original file name (for the journal)")
    migration_parser.add_argument("--manifest", help="UTF-8 JSON list of batches (file, name, source_file); use instead of --file/--name")
    migration_parser.add_argument("--field", default="last_maint_date")
    migration_parser.add_argument("--record-only", action="store_true", help="The values are already in the assets: only journal them")
    migration_parser.add_argument("--apply", action="store_true")
    demo_seed_parser = subparsers.add_parser("demo-seed", help="Load fictional demo data (works ONLY in the database toir_demo; refuses a second run)")
    demo_seed_parser.add_argument("--reset", action="store_true", help="First remove the earlier demo data (only rows marked as demo), then load it again")
    stock_parser = subparsers.add_parser(
        "stock-import",
        help="Load a 1C export (.xlsx/.csv): stock balances, supplier orders or lead times; dry-run by default",
    )
    stock_parser.add_argument("--file", required=True)
    stock_parser.add_argument("--apply", action="store_true")
    stock_parser.add_argument("--as-of", help="Balance date YYYY-MM-DD (default: today, Tashkent)")
    stock_parser.add_argument("--kind", choices=["stock", "orders", "lead_times"], help="Force the file shape (default: detect by header)")
    norms_parser = subparsers.add_parser(
        "repair-norms-import",
        help="Load cleaned repair-norm CSV files listed in a manifest (dry-run by default; refuses a set that already has lines)",
    )
    norms_parser.add_argument("--manifest", required=True)
    norms_parser.add_argument("--apply", action="store_true")
    ledger_parser = subparsers.add_parser(
        "wagon-ledger-purge",
        help="Delete SUPERSEDED wagon ledger rows older than N days (the active rows stay; dry-run by default; take a dump first)",
    )
    ledger_parser.add_argument("--older-than-days", type=int, default=14)
    ledger_parser.add_argument("--apply", action="store_true")
    health_parser = subparsers.add_parser(
        "maintenance-health", help="Check the plan invariants (--fix repairs the safe ones)"
    )
    health_parser.add_argument("--fix", action="store_true")
    baseline_parser = subparsers.add_parser(
        "maintenance-baseline-import",
        help="Import 'last service' baselines from a CSV (inv_number,interval_code,done_at,odometer_km|km,hours,note); dry-run by default",
    )
    baseline_parser.add_argument("--file", required=True)
    baseline_parser.add_argument("--apply", action="store_true")
    mileage_parser = subparsers.add_parser(
        "wagon-mileage-run",
        help="Calculate and report wagon mileage",
    )
    mileage_parser.add_argument("--dry-run", action="store_true")
    report_parser = subparsers.add_parser(
        "wagon-mileage-report", help="Read-only per-wagon mileage coverage report"
    )
    report_parser.add_argument("--csv", default=None)
    for name, text in (
        ("wagon-opening-propose", "Propose opening balances from current wagon mileage (dry-run by default)"),
        ("wagon-opening-approve", "Bulk-approve proposed opening balances (admin, maker != checker; dry-run by default)"),
    ):
        opening_parser = subparsers.add_parser(name, help=text)
        opening_parser.add_argument("--actor-email", required=True)
        opening_parser.add_argument("--effective-at", default=None)
        opening_parser.add_argument("--apply", action="store_true")
        if name == "wagon-opening-approve":
            opening_parser.add_argument(
                "--include-zero",
                action="store_true",
                help="Also approve zero-km proposals (admin confirms they start from 0)",
            )
    for name, text in (
        ("wialon-counter-release", "Release Wialon counters blocked by same-time odometer differences, only when the data prove them healthy (dry-run by default)"),
        ("asset-conflicts-clean", "Reject pending GTK number conflicts that differ only by leading zeros (dry-run by default)"),
    ):
        clean_parser = subparsers.add_parser(name, help=text)
        clean_parser.add_argument("--actor-email", default=None)
        clean_parser.add_argument("--apply", action="store_true")
        if name == "wialon-counter-release":
            clean_parser.add_argument(
                "--inv-number",
                action="append",
                help="Limit to this locomotive inventory number (repeatable); use it for a first trial",
            )
    arguments = parser.parse_args()
    if arguments.command == "wialon-health-report":
        return asyncio.run(_wialon_health_report(arguments.silent_hours, arguments.reject_days))
    if arguments.command == "audit-purge-telemetry":
        return asyncio.run(_audit_purge_telemetry(arguments.apply, max(1_000, arguments.batch_size)))
    if arguments.command == "data-migration-import":
        return asyncio.run(
            _data_migration_import(
                arguments.file, arguments.name, arguments.source_file, arguments.field, arguments.record_only, arguments.apply, arguments.manifest
            )
        )
    if arguments.command == "demo-seed":
        return asyncio.run(_demo_seed(reset=arguments.reset))
    if arguments.command == "stock-import":
        return asyncio.run(_stock_import(arguments.file, arguments.apply, arguments.as_of, arguments.kind))
    if arguments.command == "repair-norms-import":
        return asyncio.run(_repair_norms_import(arguments.manifest, arguments.apply))
    if arguments.command == "wagon-ledger-purge":
        return asyncio.run(_wagon_ledger_purge(arguments.older_than_days, arguments.apply))
    if arguments.command == "maintenance-shadow-report":
        return asyncio.run(_maintenance_shadow_report())
    if arguments.command == "maintenance-health":
        return asyncio.run(_maintenance_health(arguments.fix))
    if arguments.command == "maintenance-baseline-import":
        return asyncio.run(_maintenance_baseline_import(arguments.file, arguments.apply))
    if arguments.command == "wialon-counter-release":
        return asyncio.run(
            _wialon_counter_release(
                arguments.actor_email, arguments.apply, arguments.inv_number or None
            )
        )
    if arguments.command == "asset-conflicts-clean":
        return asyncio.run(_asset_conflicts_clean(arguments.actor_email, arguments.apply))
    if arguments.command == "wagon-mileage-report":
        return asyncio.run(_wagon_mileage_report(arguments.csv))
    if arguments.command in ("wagon-opening-propose", "wagon-opening-approve"):
        return asyncio.run(
            _wagon_opening_bulk(
                mode="propose" if arguments.command == "wagon-opening-propose" else "approve",
                actor_email=arguments.actor_email,
                effective_at=arguments.effective_at,
                apply=arguments.apply,
                include_zero=getattr(arguments, "include_zero", False),
            )
        )
    if arguments.command == "create-ad-admin":
        return asyncio.run(_create_ad_admin(arguments.email, arguments.ad_username, arguments.full_name))
    if arguments.command == "emergency-session":
        return asyncio.run(_emergency_session(arguments.admin))
    if arguments.command == "seed-reference":
        return asyncio.run(_seed_reference())
    if arguments.command == "seed-intervals":
        return asyncio.run(_seed_intervals())
    if arguments.command == "recalculate-plans":
        return asyncio.run(_recalculate_plans())
    if arguments.command == "wialon-probe":
        return asyncio.run(_wialon_probe())
    if arguments.command == "wialon-track-backfill":
        return asyncio.run(_wialon_track_backfill(arguments.days))
    if arguments.command == "gtk-gps-backfill":
        return asyncio.run(_gtk_gps_backfill(arguments.days))
    if arguments.command == "gps-analytics":
        return asyncio.run(_gps_analytics(arguments.days, arguments.wagons, arguments.diff))
    if arguments.command == "scales-rematch":
        return asyncio.run(_scales_rematch())
    if arguments.command == "wagon-mileage-run":
        return asyncio.run(_wagon_mileage_run(dry_run=arguments.dry_run))
    parser.error("Unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
