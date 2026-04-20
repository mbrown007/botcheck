"""Tests for DB tenant context wiring used by RLS policies."""

from types import SimpleNamespace

from botcheck_api.database import apply_tenant_rls_context


class _FakeSession:
    def __init__(self, dialect_name: str):
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect_name))
        self.calls: list[tuple[str, dict | None]] = []

    async def execute(self, statement, params=None):
        self.calls.append((str(statement), params))


class TestTenantRLSContext:
    async def test_apply_tenant_rls_context_sets_postgres_session_vars(self):
        session = _FakeSession("postgresql")
        await apply_tenant_rls_context(session, "acme")

        assert len(session.calls) == 2
        assert "SET LOCAL row_security = on" in session.calls[0][0]
        assert "set_config('app.tenant_id'" in session.calls[1][0]
        assert session.calls[1][1] == {"tenant_id": "acme"}

    async def test_apply_tenant_rls_context_noop_for_sqlite(self):
        session = _FakeSession("sqlite")
        await apply_tenant_rls_context(session, "acme")
        assert session.calls == []

    async def test_apply_tenant_rls_context_noop_for_no_bind(self):
        """Sessions without a bind (e.g. detached) must be a no-op."""
        session = _FakeSession("postgresql")
        session.bind = None  # type: ignore[assignment]
        await apply_tenant_rls_context(session, "acme")
        assert session.calls == []

    async def test_apply_tenant_rls_context_passes_empty_tenant_id(self):
        """Empty tenant_id is forwarded as-is; the DB policy will evaluate it
        against actual tenant values and deny access (safe default)."""
        session = _FakeSession("postgresql")
        await apply_tenant_rls_context(session, "")
        assert session.calls[1][1] == {"tenant_id": ""}
