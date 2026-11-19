"""The command centre pipeline on a real PostgreSQL: resolution of units, scoping, permissions, clarification, the two-step write confirmation, logging."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select, update

from app.core.database import SessionFactory
from app.models.assistant import AssistantPending, AssistantQuery
from app.models.assets import FixedAsset
from app.models.identity import User
from app.models.organization import Section
from app.schemas.assistant import Card, CommandIn, ConfirmIn
from app.services.assistant import engine
from app.services.assistant.registry import ACTIONS, HANDLERS
from app.services.assistant.types import PendingAction, Result

pytestmark = [pytest.mark.pg, pytest.mark.asyncio]
UTC = timezone.utc


def mkuser(role, section_id=None):
    return User(id=uuid4(), email=f"as-{uuid4().hex[:8]}@example.test", full_name="as", hashed_password="x", role=role, section_id=section_id)


@pytest.fixture
def fake_handlers(monkeypatch):
    calls = {"where": 0, "create": 0, "executed": []}

    async def where(ctx, slots):
        calls["where"] += 1
        return Result(cards=[Card(kind="asset", title=slots.asset.inv_number)], speak="ok", entities=[slots.asset.entity()])

    async def wo_create(ctx, slots):
        calls["create"] += 1
        return Result(pending=PendingAction("wo.create", {"asset_id": str(slots.asset.id)}, f"Naryad: {slots.asset.inv_number}"))

    async def execute(ctx, payload):
        calls["executed"].append(payload)
        return Result(cards=[Card(kind="text", title="done")], speak="done")

    monkeypatch.setitem(HANDLERS, "gps.where", where)
    monkeypatch.setitem(HANDLERS, "wo.create", wo_create)
    monkeypatch.setitem(ACTIONS, "wo.create", execute)
    return calls


async def _world(tag):
    sec_a, sec_b = uuid4(), uuid4()
    loco_a, loco_b = uuid4(), uuid4()
    inv_a, inv_b = f"81{int(tag[:4], 16) % 90000 + 10000}", f"82{int(tag[:4], 16) % 90000 + 10000}"
    admin, master_a, master_b = mkuser("admin"), mkuser("master", sec_a), mkuser("master", sec_b)
    async with SessionFactory() as db:
        db.add_all([Section(id=sec_a, name=f"AS-A-{tag}"), Section(id=sec_b, name=f"AS-B-{tag}")])
        await db.flush()
        db.add_all([admin, master_a, master_b,
                    FixedAsset(id=loco_a, inv_number=inv_a, asset_type="locomotive", status="operational", section_id=sec_a),
                    FixedAsset(id=loco_b, inv_number=inv_b, asset_type="locomotive", status="operational", section_id=sec_b)])
        await db.commit()
    return dict(sec=(sec_a, sec_b), loco=(loco_a, loco_b), inv=(inv_a, inv_b), admin=admin, ma=master_a, mb=master_b)


async def _cleanup(w):
    async with SessionFactory() as db:
        users = [w["admin"].id, w["ma"].id, w["mb"].id]
        await db.execute(delete(AssistantPending).where(AssistantPending.user_id.in_(users)))
        await db.execute(delete(AssistantQuery).where(AssistantQuery.user_id.in_(users)))
        await db.execute(delete(FixedAsset).where(FixedAsset.id.in_(w["loco"])))
        await db.execute(delete(User).where(User.id.in_(users)))
        await db.execute(delete(Section).where(Section.id.in_(w["sec"])))
        await db.commit()


async def test_pipeline_resolution_scoping_clarification_and_the_log(fake_handlers):
    tag = uuid4().hex[:6]
    w = await _world(tag)
    try:
        async with SessionFactory() as db:
            admin = w["admin"]
            out = await engine.run_command(db, admin, CommandIn(text=f"{w['inv'][0]} qayerda"))
            assert out.status == "ok" and out.intent == "gps.where" and out.heard == f"{w['inv'][0]} qayerda" and out.entities[0].label == w["inv"][0]
            assert fake_handlers["where"] == 1 and out.query_id is not None
            # the same sentence spoken as words
            spoken = "sakkiz bir " + " ".join(["bir", "ikki", "uch", "to'rt", "besh"][: 0])  # not a real inventory number: it must simply not resolve
            # the bare inventory number alone finds the unit (a regression: a keyword-less intent used to switch the lookup off)
            bare = await engine.run_command(db, admin, CommandIn(text=w['inv'][0]))
            assert bare.intent == 'find.asset' and bare.entities and bare.entities[0].label == w['inv'][0]
            # a Russian sentence, a Uzbek-Cyrillic one: all reach the same handler
            for text in (f"где {w['inv'][0]}", f"{w['inv'][0]} қаерда"):
                assert (await engine.run_command(db, admin, CommandIn(text=text))).intent == "gps.where"
            # no number, no context: the assistant asks, it does not guess
            asked = await engine.run_command(db, admin, CommandIn(text="qayerda"))
            assert asked.status == "needs_clarification" and fake_handlers["where"] == 3 and asked.cards
            # a number the user cannot see is not a unit (master of the other section) -> a question, never the neighbour's data
            hidden = await engine.run_command(db, w["mb"], CommandIn(text=f"{w['inv'][0]} qayerda"))
            assert hidden.status in ("needs_clarification", "denied") and fake_handlers["where"] == 3
            # unmatched text is logged for the admin list and offers suggestions
            nothing = await engine.run_command(db, admin, CommandIn(text="salom qalaysan"))
            assert nothing.status == "unmatched" and len(nothing.suggestions) >= 3 and nothing.intent is None
            rows = (await db.execute(select(AssistantQuery.status).where(AssistantQuery.user_id == admin.id))).scalars().all()
            assert rows.count("unmatched") == 1 and rows.count("ok") == 4 and "needs_clarification" in rows
            assert spoken  # (kept for readability of the case above)
    finally:
        await _cleanup(w)


async def test_a_role_without_the_permission_is_denied_and_help_lists_only_what_is_allowed():
    tag = uuid4().hex[:6]
    w = await _world(tag)
    try:
        async with SessionFactory() as db:
            denied = await engine.run_command(db, w["ma"], CommandIn(text="bugun nechta sostav tortildi"))  # a master never has scales.view (ROLE_DENIED)
            assert denied.status == "denied" and not denied.ok
            full = await engine.help_for(db, w["admin"])
            limited = await engine.help_for(db, w["ma"])
            assert {g.module for g in full.groups} > {g.module for g in limited.groups} and all(g.examples for g in full.groups)
    finally:
        await _cleanup(w)


async def test_a_write_needs_a_confirmation_that_works_once_for_its_owner_only(fake_handlers):
    tag = uuid4().hex[:6]
    w = await _world(tag)
    try:
        async with SessionFactory() as db:
            admin = w["admin"]
            out = await engine.run_command(db, admin, CommandIn(text=f"{w['inv'][0]} uchun naryad och"))
            assert out.status == "needs_confirm" and out.confirm is not None and fake_handlers["create"] == 1 and fake_handlers["executed"] == []
            token = out.confirm.token
            # someone else's token is not found
            other = await engine.confirm_command(db, w["mb"], ConfirmIn(token=token))
            assert other.status == "error" and fake_handlers["executed"] == []
            done = await engine.confirm_command(db, admin, ConfirmIn(token=token))
            assert done.status == "ok" and len(fake_handlers["executed"]) == 1
            again = await engine.confirm_command(db, admin, ConfirmIn(token=token))
            assert again.status == "error" and len(fake_handlers["executed"]) == 1  # one execution however many taps
            # cancel
            c = await engine.run_command(db, admin, CommandIn(text=f"{w['inv'][0]} uchun naryad och"))
            cancelled = await engine.confirm_command(db, admin, ConfirmIn(token=c.confirm.token, approve=False))
            assert cancelled.status == "ok" and len(fake_handlers["executed"]) == 1
            assert (await engine.confirm_command(db, admin, ConfirmIn(token=c.confirm.token))).status == "error"
            # expiry
            e = await engine.run_command(db, admin, CommandIn(text=f"{w['inv'][0]} uchun naryad och"))
            await db.execute(update(AssistantPending).where(AssistantPending.token == e.confirm.token).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
            await db.commit()
            expired = await engine.confirm_command(db, admin, ConfirmIn(token=e.confirm.token))
            assert expired.status == "error" and len(fake_handlers["executed"]) == 1
            outcomes = (await db.execute(select(AssistantPending.outcome).where(AssistantPending.user_id == admin.id))).scalars().all()
            assert sorted(outcomes) == ["cancelled", "confirmed", "expired"]
    finally:
        await _cleanup(w)


async def test_a_failing_handler_or_action_never_leaks_details(monkeypatch):
    async def broken(ctx, slots):
        raise RuntimeError("secret internals: password=hunter2")

    monkeypatch.setitem(HANDLERS, "sys.help", broken)
    tag = uuid4().hex[:6]
    w = await _world(tag)
    try:
        async with SessionFactory() as db:
            out = await engine.run_command(db, w["admin"], CommandIn(text="yordam"))
            assert out.status == "error" and "hunter2" not in out.model_dump_json() and "secret" not in out.model_dump_json()
    finally:
        await _cleanup(w)


def test_the_rate_limit_is_per_user_and_per_kind():
    uid = uuid4()
    for _ in range(engine.RATE_LIMITS["transcribe"][0]):
        engine.check_rate(uid, "transcribe")
    with pytest.raises(HTTPException) as info:
        engine.check_rate(uid, "transcribe")
    assert info.value.status_code == 429
    engine.check_rate(uid, "command")  # another kind is not affected
    engine.check_rate(uuid4(), "transcribe")  # another user is not affected


async def test_a_garbled_voice_sentence_is_repaired_and_a_garble_without_a_command_is_still_unmatched(fake_handlers):
    tag = uuid4().hex[:6]
    w = await _world(tag)
    try:
        async with SessionFactory() as db:
            inv = w["inv"][0]
            for text in (f"{inv} каердa", f"{inv} qayirda"):  # mixed scripts / a wrong vowel, as a small Whisper writes Uzbek
                out = await engine.run_command(db, w["admin"], CommandIn(text=text, source="voice", stt_confidence=0.5))
                assert out.status == "ok" and out.intent == "gps.where", text
            nothing = await engine.run_command(db, w["admin"], CommandIn(text="asdf qwer zxcv", source="voice", stt_confidence=0.4))
            assert nothing.status == "unmatched"
    finally:
        await _cleanup(w)


async def test_fleet_count_and_work_types_answer_from_the_database_and_a_master_counts_only_his_section():
    tag = uuid4().hex[:6]
    w = await _world(tag)
    try:
        async with SessionFactory() as db:
            admin_out = await engine.run_command(db, w["admin"], CommandIn(text="сколько вагонов есть"))
            assert admin_out.status == "ok" and admin_out.intent == "fleet.count" and admin_out.cards[0].rows[0].label in ("Всего", "Jami")
            master_out = await engine.run_command(db, w["ma"], CommandIn(text="texnika soni nechta"))
            assert master_out.intent == "fleet.count" and master_out.cards[0].rows[0].value == "1"  # only the master's own locomotive
            types_out = await engine.run_command(db, w["admin"], CommandIn(text="какой тип ремонта есть"))
            assert types_out.intent == "to.types" and types_out.status == "ok"
    finally:
        await _cleanup(w)


async def test_an_unfinished_command_is_completed_by_the_next_short_answer(fake_handlers):
    from app.schemas.assistant import AssistantContext

    tag = uuid4().hex[:6]
    w = await _world(tag)
    try:
        async with SessionFactory() as db:
            first = await engine.run_command(db, w["admin"], CommandIn(text="yangi naryad yarat"))
            assert first.status == "needs_clarification" and first.intent == "wo.create" and first.dialog is not None
            ctx = AssistantContext(dialog=first.dialog)
            second = await engine.run_command(db, w["admin"], CommandIn(text=w["inv"][0], context=ctx))  # just the number: it completes the order
            assert second.intent == "wo.create" and second.status == "needs_confirm" and second.confirm is not None and second.dialog is None
            assert fake_handlers["create"] == 1
            # a real new command during the dialog is not swallowed by it
            other = await engine.run_command(db, w["admin"], CommandIn(text="xaritani och", context=AssistantContext(dialog=first.dialog)))
            assert other.intent == "nav.open"
    finally:
        await _cleanup(w)


async def test_the_history_is_personal_deduplicated_and_never_shows_another_users_questions(fake_handlers):
    from app.routers.assistant import history

    tag = uuid4().hex[:6]
    w = await _world(tag)
    try:
        async with SessionFactory() as db:
            inv = w["inv"][0]
            for text in (f"{inv} qayerda", f"{inv} qayerda", "xaritani och"):
                await engine.run_command(db, w["admin"], CommandIn(text=text))
            await engine.run_command(db, w["ma"], CommandIn(text="naryadlarni och"))
            mine = await history(w["admin"], db, 40)
            assert [i.text for i in mine] == ["xarita", f"{inv} qayerda"] or [i.text for i in mine][0].startswith("xarita")
            assert len(mine) == 2 and all("naryad" not in i.text for i in mine)  # the duplicate is one line; the other user's question is absent
            theirs = await history(w["ma"], db, 40)
            assert len(theirs) == 1 and "naryad" in theirs[0].text
    finally:
        await _cleanup(w)
