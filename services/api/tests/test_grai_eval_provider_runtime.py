from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from botcheck_api import database
from botcheck_api.config import settings
from botcheck_api.grai.assertions import AssertionEvaluation
from botcheck_api.grai.eval_worker import run_grai_eval
from botcheck_api.models import GraiEvalRunRow, ProviderCredentialRow, ProviderUsageLedgerRow
from botcheck_api.providers.service import (
    encrypt_provider_secret_fields,
    ensure_provider_registry_seeded,
)

from factories import (
    make_grai_eval_run_payload,
    make_grai_eval_suite_payload,
    make_http_destination_payload,
)


@pytest.fixture(autouse=True)
def _enable_destinations(monkeypatch):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)


async def _seed_platform_provider_credential(*, provider_id: str, api_key: str) -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        await ensure_provider_registry_seeded(session, tenant_ids=[settings.tenant_id])
        now = datetime.now(UTC)
        session.add(
            ProviderCredentialRow(
                credential_id="provcred_eval_worker_test",
                owner_scope="platform",
                tenant_id=None,
                provider_id=provider_id,
                credential_source="db_encrypted",
                secret_encrypted=encrypt_provider_secret_fields({"api_key": api_key}),
                validated_at=now,
                validation_error=None,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()


async def _create_eval_run(client, user_auth_headers) -> str:
    suite_resp = await client.post(
        "/grai/suites",
        json=make_grai_eval_suite_payload(name="Worker Runtime Binding Suite"),
        headers=user_auth_headers,
    )
    assert suite_resp.status_code == 201
    suite_id = suite_resp.json()["suite_id"]

    destination_resp = await client.post(
        "/destinations/",
        json=make_http_destination_payload(name="Worker Runtime Binding Destination"),
        headers=user_auth_headers,
    )
    assert destination_resp.status_code == 201
    transport_profile_id = destination_resp.json()["transport_profile_id"]

    run_resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_profile_id,
        ),
        headers=user_auth_headers,
    )
    assert run_resp.status_code == 202
    return str(run_resp.json()["eval_run_id"])


async def test_run_grai_eval_uses_runtime_bound_anthropic_credential(client, user_auth_headers, monkeypatch):
    await _seed_platform_provider_credential(
        provider_id="anthropic:claude-sonnet-4-6",
        api_key="stored-anthropic-key",
    )
    eval_run_id = await _create_eval_run(client, user_auth_headers)
    captured: dict[str, object] = {}

    class _FakeDirectHTTPBotClient:
        def __init__(self, *, context):
            self.context = context

        async def respond(self, *, prompt, conversation, session_id, request_context=None):
            captured["prompt"] = prompt
            captured["session_id"] = session_id
            return SimpleNamespace(text="Refund policy details", latency_ms=87)

        async def aclose(self) -> None:
            return None

    async def _fake_evaluate_assertion(**kwargs):
        captured["anthropic_client"] = kwargs.get("anthropic_client")
        captured["llm_model"] = kwargs.get("llm_model")
        return AssertionEvaluation(
            assertion_type="contains",
            passed=True,
            score=1.0,
            threshold=0.8,
            weight=1.0,
            raw_value="Refund",
            failure_reason=None,
            latency_ms=None,
            input_tokens=33,
            output_tokens=11,
            request_count=1,
        )

    def _fake_anthropic_client(*, api_key: str):
        captured["anthropic_api_key"] = api_key
        return object()

    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "grai_eval_judge_model", "claude-sonnet-4-6")
    monkeypatch.setattr(
        "botcheck_api.grai.eval_worker.DirectHTTPBotClient",
        _FakeDirectHTTPBotClient,
    )
    monkeypatch.setattr(
        "botcheck_api.grai.eval_worker.evaluate_assertion",
        _fake_evaluate_assertion,
    )
    monkeypatch.setattr(
        "botcheck_api.grai.eval_worker.anthropic.AsyncAnthropic",
        _fake_anthropic_client,
    )

    result = await run_grai_eval(
        {},
        payload={"eval_run_id": eval_run_id, "tenant_id": settings.tenant_id},
    )

    assert result["status"] == "complete"
    assert captured["anthropic_api_key"] == "stored-anthropic-key"
    assert captured["llm_model"] == "claude-sonnet-4-6"
    assert captured["anthropic_client"] is not None

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        run_row = await session.get(GraiEvalRunRow, eval_run_id)
        assert run_row is not None
        assert run_row.terminal_outcome == "passed"
        ledger_rows = (
            await session.execute(
                select(ProviderUsageLedgerRow).where(
                    ProviderUsageLedgerRow.eval_run_id == eval_run_id
                )
            )
        ).scalars().all()
    assert len(ledger_rows) == 1
    assert ledger_rows[0].provider_id == "anthropic:claude-sonnet-4-6"
    assert ledger_rows[0].runtime_scope == "judge"
    assert ledger_rows[0].capability == "judge"
    assert ledger_rows[0].input_tokens == 33
    assert ledger_rows[0].output_tokens == 11
    assert ledger_rows[0].request_count == 1
