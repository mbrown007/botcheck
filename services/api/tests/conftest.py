"""Shared fixtures for API tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import botcheck_api.auth as _auth_module
from botcheck_api.auth.security import reset_auth_security_state
from botcheck_api import database
from botcheck_api.config import settings
from botcheck_api.database import get_db
from botcheck_api.main import app
from botcheck_api.models import Base, PlatformSettingsRow, TenantRow, UserRow
from botcheck_api.providers.service import ensure_provider_registry_seeded, provider_catalog_seed_by_id
from botcheck_api.admin.service_providers import (
    upsert_platform_provider_credential,
    validate_platform_provider_credential_background,
)
from botcheck_api.providers.service import provider_seed_env_secret_fields
from botcheck_api.tts_provider import reset_preview_tts_breakers

from factories import (
    make_scenario_upload_payload,
    make_scenario_yaml,
    make_sip_scenario_yaml,
)

# Low-cost Argon2id context used only within tests so the autouse db_setup
# fixture stays fast (<5ms per hash instead of ~150ms at production params).
_TEST_PWD_CONTEXT = CryptContext(
    schemes=["argon2", "pbkdf2_sha256"],
    deprecated=["pbkdf2_sha256"],
    argon2__time_cost=1,
    argon2__memory_cost=8,
    argon2__parallelism=1,
)


@pytest_asyncio.fixture(autouse=True)
async def db_setup():
    """Create a fresh in-memory SQLite DB for every test."""
    # Reset module-level singletons so init_db() doesn't skip in lifespan
    await database.close_db()

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed default local-auth user for DB-backed login flows.
    # Use _TEST_PWD_CONTEXT (low-cost) so each test setup stays fast.
    async with factory() as seed_session:
        seed_session.add(
            TenantRow(
                tenant_id=settings.tenant_id,
                slug=settings.tenant_id,
                display_name=settings.tenant_name,
                feature_overrides={},
                quota_config={},
            )
        )
        seed_session.add(
            PlatformSettingsRow(
                singleton_id="default",
                feature_flags={},
                quota_defaults={},
            )
        )
        seed_session.add(
            UserRow(
                user_id="user_test_admin",
                tenant_id=settings.tenant_id,
                email=settings.local_auth_email,
                role="admin",
                password_hash=_TEST_PWD_CONTEXT.hash(settings.local_auth_password),
                is_active=True,
                totp_enabled=False,
            )
        )
        await seed_session.commit()

    # Wire into the module so lifespan's init_db() is a no-op and get_db works
    database.engine = engine
    database.AsyncSessionLocal = factory

    # Override the FastAPI dependency
    async def _override_get_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db

    yield

    app.dependency_overrides.pop(get_db, None)
    await database.close_db()


@pytest.fixture(autouse=True)
def default_runtime_settings(monkeypatch):
    """Keep tests deterministic regardless of developer .env values."""
    monkeypatch.setattr(settings, "enable_outbound_sip", False)
    monkeypatch.setattr(settings, "enable_mock_bot", False)
    monkeypatch.setattr(settings, "openai_api_key", "test-openai-key")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "elevenlabs_api_key", "")
    monkeypatch.setattr(settings, "deepgram_api_key", "test-deepgram-key")
    monkeypatch.setattr(settings, "feature_stt_provider_deepgram_enabled", True)
    monkeypatch.setattr(settings, "feature_stt_provider_azure_enabled", False)
    monkeypatch.setattr(settings, "azure_speech_key", "")
    monkeypatch.setattr(settings, "azure_speech_region", "")
    monkeypatch.setattr(settings, "azure_speech_endpoint", "")
    monkeypatch.setattr(settings, "run_dispatch_require_harness_healthy", False)
    monkeypatch.setattr(settings, "sip_destination_allowlist", [])
    monkeypatch.setattr(settings, "local_auth_rate_limit_attempts", 1000)
    monkeypatch.setattr(settings, "local_auth_rate_limit_window_s", 60)
    monkeypatch.setattr(settings, "local_auth_lockout_failed_attempts", 5)
    monkeypatch.setattr(settings, "local_auth_lockout_duration_s", 900)
    monkeypatch.setattr(settings, "auth_totp_replay_ttl_s", 120)
    monkeypatch.setattr(settings, "auth_security_redis_enabled", False)
    reset_preview_tts_breakers()
    # Patch the module-level pwd_context to fast test params so login flows
    # and recovery-code hashing complete in <5ms per call during tests.
    monkeypatch.setattr(_auth_module, "pwd_context", _TEST_PWD_CONTEXT)
    reset_auth_security_state()


@pytest_asyncio.fixture(autouse=True)
async def managed_provider_credentials(db_setup, default_runtime_settings):
    """Seed DB-managed platform credentials from the deterministic test env."""
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        await ensure_provider_registry_seeded(session, tenant_ids=[settings.tenant_id])
        await session.commit()
        for seed in provider_catalog_seed_by_id().values():
            secret_fields = provider_seed_env_secret_fields(seed)
            if secret_fields is None:
                continue
            row = await upsert_platform_provider_credential(
                session,
                provider_id=seed.provider_id,
                secret_fields=secret_fields,
                actor_id="test-fixture",
                actor_tenant_id=settings.tenant_id,
            )
            await session.commit()
            await validate_platform_provider_credential_background(credential_id=row.credential_id)


@pytest_asyncio.fixture
async def client(db_setup):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        # Inject a mock ARQ pool so complete_run can enqueue without a real Redis
        mock_pool = MagicMock()
        mock_pool.enqueue_job = AsyncMock()
        mock_pool.set = AsyncMock()
        mock_pool.get = AsyncMock(return_value=None)
        app.state.arq_pool = mock_pool
        app.state.arq_cache_pool = mock_pool
        yield c
    app.state.arq_pool = None
    app.state.arq_cache_pool = None


@pytest.fixture
def scenario_yaml() -> str:
    return make_scenario_yaml()


@pytest.fixture
def sip_scenario_yaml() -> str:
    return make_sip_scenario_yaml()


@pytest_asyncio.fixture
async def uploaded_scenario(client, scenario_yaml, user_auth_headers) -> dict:
    """Upload a scenario and return the 201 response JSON."""
    resp = await client.post(
        "/scenarios/",
        json=make_scenario_upload_payload(scenario_yaml),
        headers=user_auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()


@pytest_asyncio.fixture
async def sip_uploaded_scenario(client, sip_scenario_yaml, user_auth_headers) -> dict:
    """Upload a SIP-protocol scenario and return the 201 response JSON."""
    resp = await client.post(
        "/scenarios/",
        json=make_scenario_upload_payload(sip_scenario_yaml),
        headers=user_auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
def user_auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.dev_user_token}"}


@pytest.fixture
def harness_auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.harness_secret}"}


@pytest.fixture
def judge_auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.judge_secret}"}


@pytest.fixture
def scheduler_auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.scheduler_secret}"}
