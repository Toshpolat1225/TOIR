from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from urllib.parse import parse_qsl
import asyncio
import json
import logging

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import RequestResponseEndpoint

from app.core.config import settings
from app.core.database import SessionFactory, engine
from app.core.localization import parse_locale
from app.core.translation_response import localize_reference_response
from app.routers.auth import router as auth_router
from app.routers.assets import router as assets_router
from app.routers.analytics import router as analytics_router
from app.routers.dashboard import router as dashboard_router
from app.routers.health import router as health_router
from app.routers.maintenance import router as maintenance_router
from app.routers.localization import router as localization_router
from app.routers.ml import router as ml_router
from app.routers.nomenclature import router as nomenclature_router
from app.routers.references import router as references_router
from app.routers.realtime import router as realtime_router
from app.routers.tmc_documents import router as tmc_documents_router
from app.routers.users import router as users_router
from app.routers.wialon import router as wialon_router
from app.routers.work_orders import router as work_orders_router
from app.realtime import dispatch_database_events, listen_for_database_events

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    listener_task = asyncio.create_task(listen_for_database_events())
    dispatcher_task = asyncio.create_task(dispatch_database_events())
    try:
        yield
    finally:
        listener_task.cancel()
        dispatcher_task.cancel()
        await asyncio.gather(listener_task, dispatcher_task, return_exceptions=True)
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
    response = await call_next(request)
    path = request.scope.get("path", "")
    localization_paths = (
        "/api/v1/sections",
        "/api/v1/departments",
        "/api/v1/work-types",
        "/api/v1/work-subtasks",
        "/api/v1/nomenclature",
        "/api/v1/fixed-assets",
        "/api/v1/work-orders",
        "/api/v1/tmc-documents",
        "/api/v1/reports",
        "/api/v1/analytics",
        "/api/v1/dashboard",
    )
    if (
        response.status_code < 300
        and any(path == prefix or path.startswith(prefix + "/") for prefix in localization_paths)
        and response.headers.get("content-type", "").startswith("application/json")
    ):
        original_body = b"".join([chunk async for chunk in response.body_iterator])
        try:
            payload = json.loads(original_body)
            async with SessionFactory() as session:
                payload = await localize_reference_response(
                    session,
                    path=path.removeprefix("/api/v1"),
                    locale=parse_locale(request.headers.get("accept-language")),
                    payload=payload,
                )
            headers = dict(response.headers)
            headers.pop("content-length", None)
            headers.pop("content-encoding", None)
            vary = {item.strip() for item in headers.get("vary", "").split(",") if item.strip()}
            vary.add("Accept-Language")
            headers["vary"] = ", ".join(sorted(vary))
            return Response(
                content=json.dumps(payload, ensure_ascii=False, default=str),
                status_code=response.status_code,
                headers=headers,
                media_type="application/json",
            )
        except Exception as exc:
            logger.warning(
                "Localization response enrichment failed (%s)",
                type(exc).__name__,
            )
            headers = dict(response.headers)
            headers.pop("content-length", None)
            headers.pop("content-encoding", None)
            return Response(
                content=original_body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.headers.get("content-type", "application/json"),
            )
    return response


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
app.include_router(maintenance_router, prefix="/api/v1")
app.include_router(localization_router, prefix="/api/v1")
app.include_router(ml_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(tmc_documents_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(realtime_router)
