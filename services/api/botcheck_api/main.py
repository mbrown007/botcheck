import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import database
from .admin import router as admin_router
from .config import settings
from .exceptions import ApiProblem, ProblemDetail
from .grai.router import router as grai_router
from .logging_setup import configure_logging
from .metrics import instrument_http
from .auth.router_login import router as auth_login_router
from .auth.router_sessions import router as auth_sessions_router
from .auth.router_totp import router as auth_totp_router
from .auth.tenants_router import router as tenants_router
from .packs.destinations_router import router as destinations_router
from .packs.router import router as packs_router
from .providers.router import router as providers_router
from .providers.tenant_router import router as tenant_provider_router
from .packs.runs_router import router as pack_runs_router
from .runs.schedules_router import router as schedules_router
from .shared.audit_router import router as audit_router
from .shared.health_router import router as health_router
from .runs.router import router as runs_router
from .scenarios.router import router as scenarios_router
from .sip_pools import router as sip_pools_router
from .telemetry import init_llm_instrumentation, instrument_app, setup_tracing
from .platform_settings_bootstrap import ensure_platform_settings_row
from .providers.service import ensure_provider_registry_seeded
from .sip_slots_startup import attempt_sip_slot_reconciliation, retry_sip_slot_reconciliation_until_ready
from .tenants_bootstrap import ensure_default_tenant
from .users_bootstrap import bootstrap_users

configure_logging(
    service="botcheck-api",
    level=settings.log_level,
    json_logs=settings.log_json,
)

logger = logging.getLogger("botcheck.api")

setup_tracing("botcheck-api")
init_llm_instrumentation()


async def _create_arq_pools() -> tuple[object, object]:
    from arq import create_pool
    from arq.connections import RedisSettings as ArqRedisSettings

    arq_pool = await create_pool(ArqRedisSettings.from_dsn(settings.redis_url))
    arq_cache_pool = await create_pool(ArqRedisSettings.from_dsn(settings.redis_url))
    return arq_pool, arq_cache_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init_db()
    app.state.sip_slots_reconcile_pending = True
    app.state.sip_slots_reconcile_task = None
    try:
        factory = database.AsyncSessionLocal
        if factory is not None:
            async with factory() as session:
                await ensure_default_tenant(session)
                await ensure_platform_settings_row(session)
                await ensure_provider_registry_seeded(session)
                if settings.users_bootstrap_enabled:
                    await bootstrap_users(session)
                await session.commit()
    except Exception:
        logger.exception("User bootstrap failed")
        raise
    try:
        app.state.arq_pool, app.state.arq_cache_pool = await _create_arq_pools()
        logger.info("ARQ pool connected to %s", settings.redis_url)
    except Exception:
        logger.warning("ARQ pool unavailable — runs will not be judged automatically")
        app.state.arq_pool = None
        app.state.arq_cache_pool = None
    try:
        await attempt_sip_slot_reconciliation(
            app,
            create_pools_fn=_create_arq_pools,
        )
    except Exception:
        logger.warning(
            "SIP slot gauge reconciliation deferred until Redis is ready",
            exc_info=True,
        )
        app.state.sip_slots_reconcile_task = asyncio.create_task(
            retry_sip_slot_reconciliation_until_ready(
                app,
                create_pools_fn=_create_arq_pools,
            )
        )
    yield
    reconcile_task = getattr(app.state, "sip_slots_reconcile_task", None)
    if reconcile_task is not None:
        reconcile_task.cancel()
        try:
            await reconcile_task
        except asyncio.CancelledError:
            pass
    await database.close_db()
    pool = getattr(app.state, "arq_pool", None)
    if pool is not None:
        await pool.close()
    cache_pool = getattr(app.state, "arq_cache_pool", None)
    if cache_pool is not None:
        await cache_pool.close()


app = FastAPI(
    title="BotCheck API",
    version="0.1.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
    lifespan=lifespan,
)
instrument_app(app)

_HTTP_TITLES: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    503: "Service Unavailable",
}


def _http_title(status: int) -> str:
    return _HTTP_TITLES.get(status, f"HTTP {status}")


@app.exception_handler(ApiProblem)
async def api_problem_handler(request, exc: ApiProblem):
    body = ProblemDetail(
        title=exc.title,
        status=exc.status,
        detail=exc.detail,
        error_code=exc.error_code,
    )
    return JSONResponse(
        status_code=exc.status,
        content=body.model_dump(exclude_none=True),
        headers={"Content-Type": "application/problem+json", **exc.headers},
    )


@app.exception_handler(HTTPException)
async def http_exception_as_problem(request, exc: HTTPException):
    if isinstance(exc.detail, str):
        detail = exc.detail
    else:
        try:
            detail = json.dumps(exc.detail)
        except (TypeError, ValueError):
            detail = str(exc.detail)
    body = ProblemDetail(
        title=_http_title(exc.status_code),
        status=exc.status_code,
        detail=detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=body.model_dump(exclude_none=True),
        headers={
            "Content-Type": "application/problem+json",
            **(exc.headers or {}),
        },
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"] if not settings.is_production else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def metrics_middleware(request, call_next):
    return await instrument_http(request, call_next)

app.include_router(health_router)
app.include_router(auth_login_router, tags=["auth"])
app.include_router(auth_totp_router, tags=["auth"])
app.include_router(auth_sessions_router, tags=["auth"])
app.include_router(tenants_router, prefix="/tenants", tags=["tenants"])
app.include_router(tenant_provider_router, prefix="/tenants", tags=["tenants"])
app.include_router(providers_router, prefix="/providers", tags=["providers"])
app.include_router(scenarios_router, prefix="/scenarios", tags=["scenarios"])
app.include_router(destinations_router, prefix="/destinations", tags=["destinations"])
app.include_router(grai_router, prefix="/grai", tags=["grai"])
app.include_router(packs_router, prefix="/packs", tags=["packs"])
app.include_router(pack_runs_router, prefix="/pack-runs", tags=["pack-runs"])
app.include_router(runs_router, prefix="/runs", tags=["runs"])
app.include_router(schedules_router, prefix="/schedules", tags=["schedules"])
app.include_router(sip_pools_router, prefix="/sip", tags=["sip"])
app.include_router(audit_router, prefix="/audit", tags=["audit"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])
