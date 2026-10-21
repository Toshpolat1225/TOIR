import argparse
import asyncio
import getpass
import sys

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import select

from app.core.database import SessionFactory, engine
from app.models.maintenance import WorkType
from app.models.organization import Department, Section
from app.services.auth import create_initial_admin

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


def _read_create_admin_inputs() -> tuple[str, str, str]:
    email = input("Admin email: ").strip()
    full_name = input("Admin full name: ").strip()
    password = getpass.getpass("Admin password: ")
    password_confirmation = getpass.getpass("Confirm password: ")
    if not email or not full_name:
        raise ValueError("Email and full name are required")
    if password != password_confirmation:
        raise ValueError("Passwords do not match")
    if not password:
        raise ValueError("Password must not be empty")
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password must not exceed 72 UTF-8 bytes")
    return email, full_name, password


async def _create_admin() -> int:
    try:
        email, full_name, password = _read_create_admin_inputs()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        async with SessionFactory() as db:
            user_id = await create_initial_admin(db, email, full_name, password)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except IntegrityError:
        print("Could not create admin; the email may already be registered.", file=sys.stderr)
        return 2
    except SQLAlchemyError:
        print("Database operation failed; verify the database connection and schema.", file=sys.stderr)
        return 2
    finally:
        await engine.dispose()

    print(f"Admin user created successfully (id: {user_id}).")
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


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("create-admin", help="Create the first administrator")
    subparsers.add_parser("seed-reference", help="Create initial directory reference data")
    arguments = parser.parse_args()
    if arguments.command == "create-admin":
        return asyncio.run(_create_admin())
    if arguments.command == "seed-reference":
        return asyncio.run(_seed_reference())
    parser.error("Unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
