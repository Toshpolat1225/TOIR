"""The demo seed must never run outside the database `toir_demo` (it writes fictional data)."""
import pytest

from app.core.config import settings
from app.services import demo_seed


@pytest.mark.asyncio
async def test_demo_seed_refuses_any_other_database(monkeypatch):
    monkeypatch.setattr(settings, "postgres_db", "toir_local")

    class Boom:
        def __getattr__(self, name):  # the guard must fire before the session is touched
            raise AssertionError("the session was used")

    with pytest.raises(ValueError, match="toir_demo"):
        await demo_seed.seed(Boom())  # type: ignore[arg-type]
