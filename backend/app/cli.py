import argparse
import asyncio
import getpass
import sys

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.database import SessionFactory, engine
from app.services.auth import create_initial_admin


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


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("create-admin", help="Create the first administrator")
    arguments = parser.parse_args()
    if arguments.command == "create-admin":
        return asyncio.run(_create_admin())
    parser.error("Unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
