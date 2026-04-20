"""Async SQLAlchemy engine + session factory.

Designed to be idempotent: calling init_db() more than once (e.g. in tests
that pre-configure the engine before the lifespan runs) is a no-op.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import settings
from .models import Base

# Module-level singletons — None until init_db() is called.
engine: AsyncEngine | None = None
AsyncSessionLocal: async_sessionmaker | None = None


async def apply_tenant_rls_context(session: AsyncSession, tenant_id: str) -> None:
    """Set PostgreSQL session context used by RLS policies.

    For non-Postgres dialects (SQLite tests/local file), this is a no-op.
    """
    bind = session.bind
    if bind is None or bind.dialect.name != "postgresql":
        return
    await session.execute(text("SET LOCAL row_security = on"))
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    )


async def init_db(url: str | None = None) -> None:
    """Initialise the engine and session factory.

    If *url* is omitted, falls back to ``settings.database_url`` then to a
    local SQLite file (``botcheck_dev.db``).  SQLite databases have their
    schema created automatically; PostgreSQL requires Alembic migrations.
    """
    global engine, AsyncSessionLocal
    if engine is not None:
        return  # already initialised — test fixture or previous call

    resolved = url or settings.database_url or "sqlite+aiosqlite:///./botcheck_dev.db"
    engine = create_async_engine(resolved, pool_pre_ping=True)
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    if resolved.startswith("sqlite"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose the engine and reset module-level singletons."""
    global engine, AsyncSessionLocal
    if engine:
        await engine.dispose()
        engine = None
        AsyncSessionLocal = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a session with auto-commit/rollback.

    RLS context is set to the configured instance tenant (settings.tenant_id).
    In v1 there is one tenant per instance, so all requests — including
    service-to-service callbacks (harness, judge) — correctly share one
    tenant_id.  Multi-tenant evolution requires per-request tenant resolution.
    """
    async with AsyncSessionLocal() as session:
        try:
            await apply_tenant_rls_context(session, settings.tenant_id)
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
