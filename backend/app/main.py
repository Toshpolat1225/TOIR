from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from urllib.parse import parse_qsl

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint

from app.core.config import settings
from app.core.database import engine
from app.routers.auth import router as auth_router
from app.routers.assets import router as assets_router
from app.routers.health import router as health_router
from app.routers.nomenclature import router as nomenclature_router
from app.routers.references import router as references_router
from app.routers.users import router as users_router
from app.routers.wialon import router as wialon_router
from app.routers.work_orders import router as work_orders_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


app = FastAPI(
    title="TOIR API",
    version="1.0.0",
    docs_url="/docs" if settings.api_docs_enabled else None,
    redoc_url="/redoc" if settings.api_docs_enabled else None,
    openapi_url="/openapi.json" if settings.api_docs_enabled else None,
    lifespan=lifespan,
)


@app.middleware("http")
async def redact_wialon_query_token(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    if request.scope.get("path") == "/api/v1/wialon/input":
        query_string = request.scope.get("query_string", b"").decode("latin-1")
        pairs = parse_qsl(query_string, keep_blank_values=True)
        tokens = [value for key, value in pairs if key.lower() == "token" and value]
        request.scope.setdefault("state", {}).update(
            {
                "wialon_query_tokens": tokens,
                "wialon_query_pairs": pairs,
                "wialon_query_size": len(request.scope.get("query_string", b"")),
            }
        )
        request.scope["query_string"] = b""
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(references_router, prefix="/api/v1")
app.include_router(nomenclature_router, prefix="/api/v1")
app.include_router(assets_router, prefix="/api/v1")
app.include_router(wialon_router, prefix="/api/v1")
app.include_router(work_orders_router, prefix="/api/v1")
