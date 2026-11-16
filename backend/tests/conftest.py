import pytest
import pytest_asyncio


@pytest_asyncio.fixture(autouse=True)
async def _fresh_engine_pool_for_pg_tests(request):
    """pg tests share one module-level engine; reset its pool per event loop."""
    if request.node.get_closest_marker("pg") is None:
        yield
        return
    from app.core.database import engine

    await engine.dispose()
    yield
    await engine.dispose()
