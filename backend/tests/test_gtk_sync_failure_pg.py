"""A failed GTK sync must be recorded (not 500) even when the session already has an open transaction (found in QA 2026-11-25)."""
import pytest
from sqlalchemy import delete, select, text

from app.core.database import SessionFactory
from app.integrations.gtk_client import GtkLoginError
from app.models.gtk import GtkSyncRun
from app.services import gtk as service


class _FailingAdapter:
    def __init__(self, *_a, **_k):
        pass

    async def fetch_gtk_snapshot(self):
        raise GtkLoginError("nope")


@pytest.mark.pg
@pytest.mark.asyncio
async def test_failed_sync_is_recorded_when_the_session_is_already_in_a_transaction(monkeypatch):
    monkeypatch.setattr(service, "GtkSourceAdapter", _FailingAdapter)
    monkeypatch.setattr(service, "_consecutive_login_failures", 0)
    monkeypatch.setattr(service, "_auto_sync_stopped", False)
    async with SessionFactory() as db:
        await db.execute(text("select 1"))  # autobegin, like an endpoint dependency that already read something
        run = await service.sync_gtk(db)
        assert run is not None and run.status == "login_failed"
        run_id = run.id
    async with SessionFactory() as db:
        assert (await db.execute(select(GtkSyncRun.status).where(GtkSyncRun.id == run_id))).scalar_one() == "login_failed"
        await db.execute(delete(GtkSyncRun).where(GtkSyncRun.id == run_id))
        await db.commit()
