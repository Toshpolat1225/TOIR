from unittest.mock import AsyncMock, patch

import pytest

from app import cli


@pytest.mark.asyncio
async def test_real_run_is_refused_when_engine_flag_is_off(capsys):
    with (
        patch.object(cli.settings, "wagon_mileage_engine_enabled", False),
        patch.object(cli, "run_wagon_mileage", new=AsyncMock()) as run,
    ):
        code = await cli._wagon_mileage_run(dry_run=False)
    assert code == 3
    run.assert_not_awaited()
    assert "WAGON_MILEAGE_ENGINE_ENABLED" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_dry_run_is_always_allowed(capsys):
    class Ctx:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_):
            return None

    with (
        patch.object(cli.settings, "wagon_mileage_engine_enabled", False),
        patch.object(cli, "SessionFactory", return_value=Ctx()),
        patch.object(cli, "engine", new=type("E", (), {"dispose": AsyncMock()})()),
        patch.object(
            cli, "run_wagon_mileage", new=AsyncMock(return_value={"dry_run": True})
        ) as run,
    ):
        code = await cli._wagon_mileage_run(dry_run=True)
    assert code == 0
    run.assert_awaited_once()
    assert run.await_args.kwargs["dry_run"] is True


@pytest.mark.asyncio
async def test_real_run_proceeds_when_flag_is_on():
    class Ctx:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_):
            return None

    with (
        patch.object(cli.settings, "wagon_mileage_engine_enabled", True),
        patch.object(cli, "SessionFactory", return_value=Ctx()),
        patch.object(cli, "engine", new=type("E", (), {"dispose": AsyncMock()})()),
        patch.object(
            cli, "run_wagon_mileage", new=AsyncMock(return_value={"dry_run": False})
        ) as run,
    ):
        code = await cli._wagon_mileage_run(dry_run=False)
    assert code == 0
    assert run.await_args.kwargs["dry_run"] is False
