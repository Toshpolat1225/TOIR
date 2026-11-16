"""Creates the temporary ZZTEST sections and users on the live system. Passwords come from a file and are never printed."""
import asyncio
import json

from sqlalchemy import select

from app.core.database import SessionFactory, engine
from app.core.security import hash_password
from app.models.identity import User
from app.models.organization import Section

ROLES = ("admin", "operator", "master", "management")


async def main():
    creds = json.load(open("/tmp/zz_creds.json"))
    ids = {"sections": {}, "users": {}}
    async with SessionFactory() as db:
        for key in ("A", "B"):
            name = f"ZZTEST-Section-{key}"
            row = (await db.execute(select(Section).where(Section.name == name))).scalar_one_or_none()
            if row is None:
                row = Section(name=name)
                db.add(row)
                await db.flush()
            ids["sections"][key] = str(row.id)
        for role in ROLES:
            email = creds[role]["email"]
            row = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if row is None:
                row = User(
                    email=email, full_name=f"ZZTEST {role}", role=role, auth_source="local", is_active=True,
                    hashed_password=hash_password(creds[role]["password"]),
                    section_id=__import__("uuid").UUID(ids["sections"]["A"]) if role == "master" else None,
                )
                db.add(row)
                await db.flush()
            ids["users"][role] = str(row.id)
        await db.commit()
    await engine.dispose()
    print(json.dumps(ids))


asyncio.run(main())
