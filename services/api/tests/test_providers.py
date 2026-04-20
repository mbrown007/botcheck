from __future__ import annotations

from datetime import UTC, datetime

import jwt
from botcheck_api import database
from botcheck_api.config import settings
from botcheck_api.models import (
    AuditLogRow,
    GraiEvalRunRow,
    ProviderCatalogRow,
    ProviderCredentialRow,
    ProviderQuotaPolicyRow,
    ProviderUsageLedgerRow,
    TenantProviderAssignmentRow,
    TenantRow,
)
from botcheck_api.providers.service import decrypt_provider_secret_fields
from botcheck_api.providers.usage_service import (
    assert_provider_quota_available,
    check_provider_quota_available,
)
from sqlalchemy import select


def _headers(role: str, *, tenant_id: str | None = None) -> dict[str, str]:
    token = jwt.encode(
        {
            "sub": f"{role}-role-user",
            "tenant_id": tenant_id or settings.tenant_id,
            "role": role,
            "iss": settings.auth_issuer,
            "iat": int(datetime.now(UTC).timestamp()),
            "amr": ["pwd", "dev_token"],
        },
        settings.secret_key,
        algorithm=settings.auth_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


def _admin_headers(*, tenant_id: str | None = None) -> dict[str, str]:
    return _headers("admin", tenant_id=tenant_id)


def _platform_admin_headers() -> dict[str, str]:
    return _headers("system_admin")


async def _seed_provider_usage_row(
    *,
    provider_id: str,
    tenant_id: str,
    usage_key: str,
    recorded_at: datetime,
    runtime_scope: str,
    capability: str,
    run_id: str | None = None,
    eval_run_id: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    audio_seconds: float = 0.0,
    characters: int = 0,
    sip_minutes: float = 0.0,
    request_count: int = 1,
    calculated_cost_microcents: int | None = None,
) -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        session.add(
            ProviderUsageLedgerRow(
                ledger_id=f"provusage_{usage_key}",
                usage_key=usage_key,
                tenant_id=tenant_id,
                provider_id=provider_id,
                runtime_scope=runtime_scope,
                capability=capability,
                run_id=run_id,
                eval_run_id=eval_run_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                audio_seconds=audio_seconds,
                characters=characters,
                sip_minutes=sip_minutes,
                request_count=request_count,
                calculated_cost_microcents=calculated_cost_microcents,
                recorded_at=recorded_at,
            )
        )
        await session.commit()


async def _seed_grai_eval_run_row(
    *,
    eval_run_id: str,
    tenant_id: str,
    status: str,
    terminal_outcome: str | None,
) -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        now = datetime.now(UTC)
        session.add(
            GraiEvalRunRow(
                eval_run_id=eval_run_id,
                tenant_id=tenant_id,
                suite_id="gesuite_provider_usage",
                transport_profile_id="dest_http_provider_usage",
                endpoint_at_start="https://bot.internal/chat",
                headers_at_start={},
                direct_http_config_at_start=None,
                trigger_source="manual",
                schedule_id=None,
                triggered_by="provider-test",
                status=status,
                terminal_outcome=terminal_outcome,
                prompt_count=1,
                case_count=1,
                total_pairs=1,
                dispatched_count=1,
                completed_count=1 if terminal_outcome == "passed" else 0,
                failed_count=1 if terminal_outcome == "assertion_failed" else 0,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()


async def _seed_provider_quota_policy_row(
    *,
    quota_policy_id: str,
    tenant_id: str,
    provider_id: str,
    metric: str,
    limit_per_day: int,
    soft_limit_pct: int = 80,
) -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        session.add(
            ProviderQuotaPolicyRow(
                quota_policy_id=quota_policy_id,
                tenant_id=tenant_id,
                provider_id=provider_id,
                metric=metric,
                limit_per_day=limit_per_day,
                soft_limit_pct=soft_limit_pct,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        await session.commit()


async def _clear_platform_provider_credentials(*, provider_id: str | None = None) -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        query = select(ProviderCredentialRow).where(
            ProviderCredentialRow.owner_scope == "platform",
            ProviderCredentialRow.tenant_id.is_(None),
        )
        if provider_id is not None:
            query = query.where(ProviderCredentialRow.provider_id == provider_id)
        rows = list((await session.execute(query)).scalars().all())
        for row in rows:
            await session.delete(row)
        await session.commit()


async def test_available_providers_returns_seeded_runtime_inventory(client, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-anthropic-key")
    import_resp = await client.post(
        "/admin/providers/import-env-credentials",
        headers=_platform_admin_headers(),
    )
    assert import_resp.status_code == 200

    resp = await client.get("/providers/available", headers=_admin_headers())

    assert resp.status_code == 200
    payload = resp.json()
    items = {item["provider_id"]: item for item in payload["items"]}
    assert "openai:gpt-4o-mini-tts" in items
    assert "openai:gpt-4o" in items
    assert "openai:gpt-4o-mini" in items
    assert "anthropic:claude-sonnet-4-6" in items
    assert "anthropic:claude-sonnet-4-5-20251001" in items
    assert "deepgram:nova-2-general" in items
    assert "elevenlabs:eleven_flash_v2_5" not in items
    assert "azure:azure-speech" not in items
    assert items["deepgram:nova-2-general"]["configured"] is True
    assert items["deepgram:nova-2-general"]["credential_source"] == "db_encrypted"
    assert items["deepgram:nova-2-general"]["availability_status"] == "available"


async def test_available_providers_applies_tenant_feature_overrides(
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_tts_provider_elevenlabs_enabled", False)
    monkeypatch.setattr(settings, "elevenlabs_api_key", "test-elevenlabs-key")
    import_resp = await client.post(
        "/admin/providers/import-env-credentials",
        headers=_platform_admin_headers(),
    )
    assert import_resp.status_code == 200

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        tenant = (
            await session.execute(
                select(TenantRow).where(TenantRow.tenant_id == settings.tenant_id)
            )
        ).scalar_one()
        tenant.feature_overrides = {
            "feature_tts_provider_openai_enabled": False,
            "feature_tts_provider_elevenlabs_enabled": True,
        }
        await session.commit()

    resp = await client.get("/providers/available", headers=_admin_headers())

    assert resp.status_code == 200
    items = {item["provider_id"]: item for item in resp.json()["items"]}
    assert "elevenlabs:eleven_flash_v2_5" in items
    assert "openai:gpt-4o-mini-tts" not in items
    assert "openai:gpt-4o" in items


async def test_admin_provider_inventory_requires_platform_admin(client):
    resp = await client.get("/admin/providers/", headers=_admin_headers())
    assert resp.status_code == 403


async def test_admin_provider_inventory_shows_single_assignee_shape(
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-anthropic-key")
    import_resp = await client.post(
        "/admin/providers/import-env-credentials",
        headers=_platform_admin_headers(),
    )
    assert import_resp.status_code == 200

    create_resp = await client.post(
        "/admin/tenants/",
        json={
            "tenant_id": "acme",
            "slug": "acme",
            "display_name": "Acme Corp",
            "feature_overrides": {},
            "quota_config": {},
        },
        headers=_platform_admin_headers(),
    )
    assert create_resp.status_code == 201

    resp = await client.get("/admin/providers/", headers=_platform_admin_headers())

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 8
    items = {item["provider_id"]: item for item in payload["items"]}
    assert items["openai:gpt-4o-mini-tts"]["configured"] is True
    assert items["openai:gpt-4o-mini-tts"]["available"] is True
    assert items["openai:gpt-4o-mini-tts"]["tenant_assignment_count"] == 1
    assert items["openai:gpt-4o-mini-tts"]["assigned_tenant"]["tenant_id"] == settings.tenant_id
    assert items["deepgram:nova-2-general"]["configured"] is True
    assert items["deepgram:nova-2-general"]["available"] is True
    assert items["deepgram:nova-2-general"]["credential_source"] == "db_encrypted"
    assert items["deepgram:nova-2-general"]["availability_status"] == "available"

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        catalog_count = len(
            list((await session.execute(select(ProviderCatalogRow.provider_id))).scalars().all())
        )
        assignment_rows = (
            await session.execute(
                select(TenantProviderAssignmentRow).where(
                    TenantProviderAssignmentRow.tenant_id == "acme"
                )
            )
        ).scalars().all()
    assert catalog_count == 8
    assert len(assignment_rows) == 0


async def test_admin_provider_label_can_be_updated(client, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-anthropic-key")
    import_resp = await client.post(
        "/admin/providers/import-env-credentials",
        headers=_platform_admin_headers(),
    )
    assert import_resp.status_code == 200

    resp = await client.patch(
        "/admin/providers/openai:gpt-4o-mini-tts",
        json={"label": "Primary voice"},
        headers=_platform_admin_headers(),
    )

    assert resp.status_code == 200
    assert resp.json()["label"] == "Primary voice"

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        row = await session.get(ProviderCatalogRow, "openai:gpt-4o-mini-tts")
        assert row is not None
        assert row.label == "Primary voice"


async def test_admin_provider_label_update_requires_platform_admin(client):
    resp = await client.patch(
        "/admin/providers/openai:gpt-4o-mini-tts",
        json={"label": "Should fail"},
        headers=_admin_headers(),
    )
    assert resp.status_code == 403


async def test_admin_provider_label_update_returns_404_for_unknown_provider(client):
    resp = await client.patch(
        "/admin/providers/nonexistent:provider-id",
        json={"label": "Ghost"},
        headers=_platform_admin_headers(),
    )
    assert resp.status_code == 404


async def test_admin_provider_label_can_be_cleared(client, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-anthropic-key")
    await client.post(
        "/admin/providers/import-env-credentials",
        headers=_platform_admin_headers(),
    )
    # Set a label first
    await client.patch(
        "/admin/providers/openai:gpt-4o-mini-tts",
        json={"label": "Temporary label"},
        headers=_platform_admin_headers(),
    )
    # Clear it with null
    resp = await client.patch(
        "/admin/providers/openai:gpt-4o-mini-tts",
        json={"label": None},
        headers=_platform_admin_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["label"] is None

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        row = await session.get(ProviderCatalogRow, "openai:gpt-4o-mini-tts")
        assert row is not None
        assert row.label is None


async def test_admin_provider_import_env_credentials_imports_seeded_provider_secrets(
    client,
    monkeypatch,
):
    await _clear_platform_provider_credentials()
    monkeypatch.setattr(settings, "anthropic_api_key", "test-anthropic-key")
    monkeypatch.setattr(settings, "deepgram_api_key", "")
    monkeypatch.setattr(settings, "elevenlabs_api_key", "")

    resp = await client.post(
        "/admin/providers/import-env-credentials",
        headers=_platform_admin_headers(),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["imported_count"] == 5
    item_status = {item["provider_id"]: item for item in body["items"]}
    assert item_status["openai:gpt-4o-mini-tts"]["status"] == "imported"
    assert item_status["anthropic:claude-sonnet-4-6"]["status"] == "imported"

    inventory = await client.get("/admin/providers/", headers=_platform_admin_headers())
    assert inventory.status_code == 200
    items = {item["provider_id"]: item for item in inventory.json()["items"]}
    assert items["openai:gpt-4o-mini-tts"]["credential_source"] == "db_encrypted"
    assert items["openai:gpt-4o-mini-tts"]["platform_credential"]["has_stored_secret"] is True
    assert items["anthropic:claude-sonnet-4-6"]["credential_source"] == "db_encrypted"
    assert items["anthropic:claude-sonnet-4-6"]["platform_credential"]["has_stored_secret"] is True


async def test_admin_provider_import_env_credentials_requires_platform_admin(client):
    for role in ("viewer", "operator", "editor", "admin"):
        resp = await client.post(
            "/admin/providers/import-env-credentials",
            headers=_headers(role),
        )
        assert resp.status_code == 403, f"expected 403 for role={role}, got {resp.status_code}"


async def test_admin_provider_import_env_credentials_idempotent(
    client,
    monkeypatch,
):
    await _clear_platform_provider_credentials()
    monkeypatch.setattr(settings, "openai_api_key", "test-openai-key")
    monkeypatch.setattr(settings, "deepgram_api_key", "")
    monkeypatch.setattr(settings, "elevenlabs_api_key", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "azure_speech_key", "")

    resp1 = await client.post(
        "/admin/providers/import-env-credentials",
        headers=_platform_admin_headers(),
    )
    assert resp1.status_code == 200
    body1 = resp1.json()
    assert body1["imported_count"] >= 1
    openai_item = next(
        (i for i in body1["items"] if i["provider_id"] == "openai:gpt-4o-mini-tts"),
        None,
    )
    assert openai_item is not None
    assert openai_item["status"] == "imported"

    # Second import — already-stored credentials must be skipped, not overwritten
    resp2 = await client.post(
        "/admin/providers/import-env-credentials",
        headers=_platform_admin_headers(),
    )
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["imported_count"] == 0
    openai_item2 = next(
        (i for i in body2["items"] if i["provider_id"] == "openai:gpt-4o-mini-tts"),
        None,
    )
    assert openai_item2 is not None
    assert openai_item2["status"] == "skipped"


async def test_available_providers_rejects_unauthenticated(client):
    resp = await client.get("/providers/available")
    assert resp.status_code == 401


async def test_admin_provider_inventory_rejects_sub_system_admin_roles(client):
    for role in ("viewer", "operator", "editor", "admin"):
        resp = await client.get("/admin/providers/", headers=_headers(role))
        assert resp.status_code == 403, f"expected 403 for role={role}, got {resp.status_code}"


async def test_available_providers_tenant_assignments_are_isolated(client):
    # Seed a second tenant with feature overrides that disable openai TTS.
    # Verify the default tenant's provider list is unaffected (no cross-tenant bleed).
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        session.add(
            TenantRow(
                tenant_id="tenant_b_isolation",
                slug="tenant-b-isolation",
                display_name="Tenant B",
                feature_overrides={"feature_tts_provider_openai_enabled": False},
                quota_config={},
            )
        )
        await session.commit()

    resp = await client.get("/providers/available", headers=_headers("viewer"))
    assert resp.status_code == 200
    ids = {item["provider_id"] for item in resp.json()["items"]}
    # Default tenant still sees openai TTS — tenant B's feature overrides must not bleed
    assert "openai:gpt-4o-mini-tts" in ids

    # Every returned item must be assigned to the default tenant, not tenant B
    async with factory() as session:
        default_assignment_ids = set(
            (
                await session.execute(
                    select(TenantProviderAssignmentRow.provider_id).where(
                        TenantProviderAssignmentRow.tenant_id == settings.tenant_id
                    )
                )
            ).scalars().all()
        )
    assert ids <= default_assignment_ids  # response is a subset of the default tenant's assignments


async def test_admin_provider_credential_upsert_encrypts_validates_and_audits(client):
    resp = await client.post(
        "/admin/providers/openai:gpt-4o-mini-tts/credentials",
        json={"secret_fields": {"api_key": "stored-openai-key"}},
        headers=_platform_admin_headers(),
    )

    assert resp.status_code == 202
    payload = resp.json()
    assert payload["provider_id"] == "openai:gpt-4o-mini-tts"
    assert payload["credential_source"] == "db_encrypted"
    assert payload["validation_status"] == "pending"

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        credential = (
            await session.execute(
                select(ProviderCredentialRow).where(
                    ProviderCredentialRow.owner_scope == "platform",
                    ProviderCredentialRow.tenant_id.is_(None),
                    ProviderCredentialRow.provider_id == "openai:gpt-4o-mini-tts",
                )
            )
        ).scalar_one()
        assert credential.secret_encrypted is not None
        assert "stored-openai-key" not in credential.secret_encrypted
        assert decrypt_provider_secret_fields(credential.secret_encrypted) == {"api_key": "stored-openai-key"}
        assert credential.validated_at is not None
        assert credential.validation_error is None
        audit_actions = set(
            (
                await session.execute(
                    select(AuditLogRow.action).where(
                        AuditLogRow.resource_type == "provider",
                        AuditLogRow.resource_id == "openai:gpt-4o-mini-tts",
                    )
                )
            ).scalars().all()
        )
    assert "provider_credential.created" in audit_actions

    inventory = await client.get("/admin/providers/", headers=_platform_admin_headers())
    assert inventory.status_code == 200
    items = {item["provider_id"]: item for item in inventory.json()["items"]}
    assert items["openai:gpt-4o-mini-tts"]["credential_source"] == "db_encrypted"
    assert items["openai:gpt-4o-mini-tts"]["platform_credential"]["validation_status"] == "valid"


async def test_admin_provider_credential_delete_removes_row_and_audits(client):
    create_resp = await client.post(
        "/admin/providers/openai:gpt-4o-mini-tts/credentials",
        json={"secret_fields": {"api_key": "stored-openai-key"}},
        headers=_platform_admin_headers(),
    )
    assert create_resp.status_code == 202

    delete_resp = await client.delete(
        "/admin/providers/openai:gpt-4o-mini-tts/credentials",
        headers=_platform_admin_headers(),
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["credential_source"] == "db_encrypted"

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        credential = (
            await session.execute(
                select(ProviderCredentialRow).where(
                    ProviderCredentialRow.owner_scope == "platform",
                    ProviderCredentialRow.tenant_id.is_(None),
                    ProviderCredentialRow.provider_id == "openai:gpt-4o-mini-tts",
                )
            )
        ).scalar_one_or_none()
        assert credential is None
        audit_actions = set(
            (
                await session.execute(
                    select(AuditLogRow.action).where(
                        AuditLogRow.resource_type == "provider",
                        AuditLogRow.resource_id == "openai:gpt-4o-mini-tts",
                    )
                )
            ).scalars().all()
        )
    assert "provider_credential.deleted" in audit_actions


async def test_internal_provider_runtime_context_returns_db_secret_fields(
    client,
    harness_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "openai_api_key", "")

    create_resp = await client.post(
        "/admin/providers/openai:gpt-4o-mini-tts/credentials",
        json={"secret_fields": {"api_key": "stored-openai-key"}},
        headers=_platform_admin_headers(),
    )
    assert create_resp.status_code == 202

    resp = await client.post(
        "/providers/internal/runtime-context",
        json={
            "tenant_id": settings.tenant_id,
            "runtime_scope": "agent",
            "tts_voice": "openai:alloy",
            "stt_provider": "deepgram",
            "stt_model": "nova-2-general",
        },
        headers=harness_auth_headers,
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["tenant_id"] == settings.tenant_id
    assert payload["runtime_scope"] == "agent"
    assert payload["tts"]["credential_source"] == "db_encrypted"
    assert payload["tts"]["secret_fields"] == {"api_key": "stored-openai-key"}
    assert payload["tts"]["availability_status"] == "available"
    assert payload["stt"]["vendor"] == "deepgram"
    assert payload["providers"] == []


async def test_internal_provider_runtime_context_returns_judge_provider_binding(
    client,
    judge_auth_headers,
    monkeypatch,
):
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    create_resp = await client.post(
        "/admin/providers/anthropic:claude-sonnet-4-6/credentials",
        json={"secret_fields": {"api_key": "stored-anthropic-key"}},
        headers=_platform_admin_headers(),
    )
    assert create_resp.status_code == 202

    resp = await client.post(
        "/providers/internal/runtime-context",
        json={
            "tenant_id": settings.tenant_id,
            "runtime_scope": "judge",
            "provider_bindings": [
                {
                    "capability": "judge",
                    "model": "claude-sonnet-4-6",
                }
            ],
        },
        headers=judge_auth_headers,
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["providers"] == [
        {
            "capability": "judge",
            "vendor": "anthropic",
            "model": "claude-sonnet-4-6",
            "provider_id": "anthropic:claude-sonnet-4-6",
            "credential_source": "db_encrypted",
            "availability_status": "available",
            "secret_fields": {"api_key": "stored-anthropic-key"},
        }
    ]


async def test_internal_provider_usage_route_records_usage_row(client, judge_auth_headers):
    payload = {
        "tenant_id": settings.tenant_id,
        "provider_id": "anthropic:claude-sonnet-4-6",
        "usage_key": "judge-run:run_usage_test:anthropic:claude-sonnet-4-6",
        "runtime_scope": "judge",
        "capability": "judge",
        "run_id": "run_usage_test",
        "input_tokens": 123,
        "output_tokens": 45,
        "request_count": 2,
    }
    resp = await client.post(
        "/providers/internal/usage",
        json=payload,
        headers=judge_auth_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["stored"] is True
    assert body["ledger_id"].startswith("provusage_")

    second_resp = await client.post(
        "/providers/internal/usage",
        json={**payload, "input_tokens": 200, "output_tokens": 80, "request_count": 3},
        headers=judge_auth_headers,
    )
    assert second_resp.status_code == 200
    second_body = second_resp.json()
    assert second_body["stored"] is True
    assert second_body["ledger_id"] == body["ledger_id"]

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        rows = (
            await session.execute(
                select(ProviderUsageLedgerRow).where(
                    ProviderUsageLedgerRow.usage_key == payload["usage_key"]
                )
            )
        ).scalars().all()
        assert len(rows) == 1
        row = rows[0]
        assert row.ledger_id == body["ledger_id"]
        assert row.tenant_id == settings.tenant_id
        assert row.provider_id == "anthropic:claude-sonnet-4-6"
        assert row.runtime_scope == "judge"
        assert row.capability == "judge"
        assert row.run_id == "run_usage_test"
        assert row.input_tokens == 200
        assert row.output_tokens == 80
        assert row.request_count == 3


async def test_internal_provider_usage_route_returns_stored_false_for_capability_mismatch(
    client,
    judge_auth_headers,
):
    resp = await client.post(
        "/providers/internal/usage",
        json={
            "tenant_id": settings.tenant_id,
            "provider_id": "anthropic:claude-sonnet-4-6",
            "usage_key": "judge-run:run_usage_bad:anthropic:claude-sonnet-4-6",
            "runtime_scope": "judge",
            "capability": "tts",
            "run_id": "run_usage_bad",
            "input_tokens": 10,
            "output_tokens": 5,
            "request_count": 1,
        },
        headers=judge_auth_headers,
    )

    assert resp.status_code == 200
    assert resp.json() == {"stored": False, "ledger_id": None}


async def test_tenant_provider_usage_rollup_excludes_non_finalized_and_failed_grai_usage(client):
    now = datetime.now(UTC)
    await _seed_provider_usage_row(
        provider_id="openai:gpt-4o-mini-tts",
        tenant_id=settings.tenant_id,
        usage_key="usage_tts_default",
        recorded_at=now,
        runtime_scope="agent",
        capability="tts",
        run_id="run_tts_default",
        characters=120,
        request_count=2,
        calculated_cost_microcents=240,
    )
    await _seed_grai_eval_run_row(
        eval_run_id="gerun_usage_passed",
        tenant_id=settings.tenant_id,
        status="complete",
        terminal_outcome="passed",
    )
    await _seed_provider_usage_row(
        provider_id="anthropic:claude-sonnet-4-6",
        tenant_id=settings.tenant_id,
        usage_key="usage_judge_passed",
        recorded_at=now,
        runtime_scope="judge",
        capability="judge",
        eval_run_id="gerun_usage_passed",
        input_tokens=40,
        output_tokens=10,
        request_count=1,
        calculated_cost_microcents=500,
    )
    await _seed_grai_eval_run_row(
        eval_run_id="gerun_usage_failed",
        tenant_id=settings.tenant_id,
        status="failed",
        terminal_outcome="execution_failed",
    )
    await _seed_provider_usage_row(
        provider_id="anthropic:claude-sonnet-4-6",
        tenant_id=settings.tenant_id,
        usage_key="usage_judge_failed",
        recorded_at=now,
        runtime_scope="judge",
        capability="judge",
        eval_run_id="gerun_usage_failed",
        input_tokens=999,
        output_tokens=999,
        request_count=9,
        calculated_cost_microcents=9999,
    )
    await _seed_provider_usage_row(
        provider_id="openai:gpt-4o-mini",
        tenant_id="other_usage_tenant",
        usage_key="usage_other_tenant",
        recorded_at=now,
        runtime_scope="api",
        capability="llm",
        input_tokens=300,
        output_tokens=100,
        request_count=1,
        calculated_cost_microcents=3000,
    )

    resp = await client.get("/tenants/me/providers/usage", headers=_headers("operator"))

    assert resp.status_code == 200
    body = resp.json()
    items = {item["provider_id"]: item for item in body["items"]}
    assert set(items) == {"openai:gpt-4o-mini-tts", "anthropic:claude-sonnet-4-6"}
    assert items["openai:gpt-4o-mini-tts"]["characters_24h"] == 120
    assert items["openai:gpt-4o-mini-tts"]["request_count_24h"] == 2
    assert items["openai:gpt-4o-mini-tts"]["calculated_cost_microcents_24h"] == 240
    assert items["anthropic:claude-sonnet-4-6"]["input_tokens_24h"] == 40
    assert items["anthropic:claude-sonnet-4-6"]["output_tokens_24h"] == 10
    assert items["anthropic:claude-sonnet-4-6"]["request_count_24h"] == 1
    assert items["anthropic:claude-sonnet-4-6"]["calculated_cost_microcents_24h"] == 500


async def test_tenant_provider_quota_rollup_uses_24h_usage_and_terminal_outcome_filter(client):
    now = datetime.now(UTC)
    await _seed_provider_quota_policy_row(
        quota_policy_id="quota_openai_chars",
        tenant_id=settings.tenant_id,
        provider_id="openai:gpt-4o-mini-tts",
        metric="characters",
        limit_per_day=200,
        soft_limit_pct=75,
    )
    await _seed_provider_quota_policy_row(
        quota_policy_id="quota_anthropic_input",
        tenant_id=settings.tenant_id,
        provider_id="anthropic:claude-sonnet-4-6",
        metric="input_tokens",
        limit_per_day=100,
        soft_limit_pct=70,
    )
    await _seed_provider_quota_policy_row(
        quota_policy_id="quota_anthropic_requests",
        tenant_id=settings.tenant_id,
        provider_id="anthropic:claude-sonnet-4-6",
        metric="requests",
        limit_per_day=1,
        soft_limit_pct=80,
    )
    await _seed_provider_usage_row(
        provider_id="openai:gpt-4o-mini-tts",
        tenant_id=settings.tenant_id,
        usage_key="quota_tts_default",
        recorded_at=now,
        runtime_scope="agent",
        capability="tts",
        characters=120,
        request_count=2,
        calculated_cost_microcents=240,
    )
    await _seed_grai_eval_run_row(
        eval_run_id="gerun_quota_assertion_failed",
        tenant_id=settings.tenant_id,
        status="failed",
        terminal_outcome="assertion_failed",
    )
    await _seed_provider_usage_row(
        provider_id="anthropic:claude-sonnet-4-6",
        tenant_id=settings.tenant_id,
        usage_key="quota_judge_assertion_failed",
        recorded_at=now,
        runtime_scope="judge",
        capability="judge",
        eval_run_id="gerun_quota_assertion_failed",
        input_tokens=80,
        output_tokens=20,
        request_count=1,
        calculated_cost_microcents=800,
    )
    await _seed_grai_eval_run_row(
        eval_run_id="gerun_quota_cancelled",
        tenant_id=settings.tenant_id,
        status="cancelled",
        terminal_outcome="cancelled",
    )
    await _seed_provider_usage_row(
        provider_id="anthropic:claude-sonnet-4-6",
        tenant_id=settings.tenant_id,
        usage_key="quota_judge_cancelled",
        recorded_at=now,
        runtime_scope="judge",
        capability="judge",
        eval_run_id="gerun_quota_cancelled",
        input_tokens=500,
        output_tokens=100,
        request_count=4,
        calculated_cost_microcents=5000,
    )

    resp = await client.get("/tenants/me/providers/quota", headers=_headers("operator"))

    assert resp.status_code == 200
    body = resp.json()
    items = {item["provider_id"]: item for item in body["items"]}
    assert set(items) == {"openai:gpt-4o-mini-tts", "anthropic:claude-sonnet-4-6"}

    openai_metrics = {item["metric"]: item for item in items["openai:gpt-4o-mini-tts"]["metrics"]}
    assert openai_metrics["characters"]["used_24h"] == 120
    assert openai_metrics["characters"]["remaining_24h"] == 80
    assert openai_metrics["characters"]["status"] == "healthy"

    anthropic_metrics = {item["metric"]: item for item in items["anthropic:claude-sonnet-4-6"]["metrics"]}
    assert anthropic_metrics["input_tokens"]["used_24h"] == 80
    assert anthropic_metrics["input_tokens"]["remaining_24h"] == 20
    assert anthropic_metrics["input_tokens"]["status"] == "watch"
    assert anthropic_metrics["requests"]["used_24h"] == 1
    assert anthropic_metrics["requests"]["status"] == "exceeded"


async def test_check_provider_quota_available_uses_estimated_request_increment() -> None:
    await _seed_provider_quota_policy_row(
        quota_policy_id="quota_requests_check",
        tenant_id=settings.tenant_id,
        provider_id="anthropic:claude-sonnet-4-6",
        metric="requests",
        limit_per_day=5,
        soft_limit_pct=60,
    )
    now = datetime.now(UTC)
    await _seed_provider_usage_row(
        provider_id="anthropic:claude-sonnet-4-6",
        tenant_id=settings.tenant_id,
        usage_key="usage_requests_check",
        recorded_at=now,
        runtime_scope="judge",
        capability="judge",
        request_count=4,
    )

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        result = await check_provider_quota_available(
            session,
            tenant_id=settings.tenant_id,
            provider_id="anthropic:claude-sonnet-4-6",
            runtime_scope="judge",
            capability="judge",
            estimated_usage={"requests": 2},
        )

    assert result.blocked is True
    # With projected=6 and soft_limit_pct=60 on a limit of 5 (soft threshold=3),
    # both hard and soft limits are crossed — warning is preserved independently.
    assert result.warning is True
    assert result.decisions[0].metric == "requests"
    assert result.decisions[0].projected_24h == 6.0


async def test_assert_provider_quota_available_allows_and_flags_soft_limit() -> None:
    await _seed_provider_quota_policy_row(
        quota_policy_id="quota_soft_limit",
        tenant_id=settings.tenant_id,
        provider_id="openai:gpt-4o-mini-tts",
        metric="characters",
        limit_per_day=100,
        soft_limit_pct=70,
    )
    now = datetime.now(UTC)
    await _seed_provider_usage_row(
        provider_id="openai:gpt-4o-mini-tts",
        tenant_id=settings.tenant_id,
        usage_key="usage_soft_limit",
        recorded_at=now,
        runtime_scope="api",
        capability="tts",
        characters=60,
        request_count=1,
    )

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        result = await assert_provider_quota_available(
            session,
            tenant_id=settings.tenant_id,
            provider_id="openai:gpt-4o-mini-tts",
            runtime_scope="api",
            capability="tts",
            source="preview_tts",
            estimated_usage={"characters": 20, "requests": 1},
        )

    assert result.blocked is False
    assert result.warning is True
    assert result.decisions[0].metric == "characters"
    assert result.decisions[0].projected_24h == 80.0


async def test_tenant_provider_usage_routes_require_operator_minimum(client):
    usage_viewer = await client.get("/tenants/me/providers/usage", headers=_headers("viewer"))
    quota_viewer = await client.get("/tenants/me/providers/quota", headers=_headers("viewer"))
    usage_operator = await client.get("/tenants/me/providers/usage", headers=_headers("operator"))
    quota_operator = await client.get("/tenants/me/providers/quota", headers=_headers("operator"))

    assert usage_viewer.status_code == 403
    assert quota_viewer.status_code == 403
    assert usage_operator.status_code == 200
    assert quota_operator.status_code == 200


async def test_admin_provider_usage_summary_returns_provider_specific_rollup(client):
    now = datetime.now(UTC)
    await _seed_provider_usage_row(
        provider_id="openai:gpt-4o-mini-tts",
        tenant_id=settings.tenant_id,
        usage_key="admin_usage_tts_default",
        recorded_at=now,
        runtime_scope="agent",
        capability="tts",
        characters=180,
        request_count=3,
        calculated_cost_microcents=360,
    )

    resp = await client.get(
        "/admin/providers/openai:gpt-4o-mini-tts/usage",
        headers=_platform_admin_headers(),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["item"]["provider_id"] == "openai:gpt-4o-mini-tts"
    assert body["item"]["characters_24h"] == 180
    assert body["item"]["request_count_24h"] == 3
    assert body["item"]["calculated_cost_microcents_24h"] == 360


async def test_admin_provider_quota_summary_returns_provider_specific_metrics(client):
    now = datetime.now(UTC)
    await _seed_provider_quota_policy_row(
        quota_policy_id="admin_quota_openai_chars",
        tenant_id=settings.tenant_id,
        provider_id="openai:gpt-4o-mini-tts",
        metric="characters",
        limit_per_day=200,
        soft_limit_pct=75,
    )
    await _seed_provider_usage_row(
        provider_id="openai:gpt-4o-mini-tts",
        tenant_id=settings.tenant_id,
        usage_key="admin_quota_tts_default",
        recorded_at=now,
        runtime_scope="agent",
        capability="tts",
        characters=120,
        request_count=2,
        calculated_cost_microcents=240,
    )

    resp = await client.get(
        "/admin/providers/openai:gpt-4o-mini-tts/quota",
        headers=_platform_admin_headers(),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["item"]["provider_id"] == "openai:gpt-4o-mini-tts"
    metrics = {item["metric"]: item for item in body["item"]["metrics"]}
    assert metrics["characters"]["used_24h"] == 120
    assert metrics["characters"]["remaining_24h"] == 80
    assert metrics["characters"]["status"] == "healthy"


async def test_admin_provider_usage_and_quota_routes_require_platform_admin(client):
    usage_admin = await client.get(
        "/admin/providers/openai:gpt-4o-mini-tts/usage",
        headers=_admin_headers(),
    )
    quota_admin = await client.get(
        "/admin/providers/openai:gpt-4o-mini-tts/quota",
        headers=_admin_headers(),
    )
    usage_platform_admin = await client.get(
        "/admin/providers/openai:gpt-4o-mini-tts/usage",
        headers=_platform_admin_headers(),
    )
    quota_platform_admin = await client.get(
        "/admin/providers/openai:gpt-4o-mini-tts/quota",
        headers=_platform_admin_headers(),
    )

    assert usage_admin.status_code == 403
    assert quota_admin.status_code == 403
    assert usage_platform_admin.status_code == 200
    assert quota_platform_admin.status_code == 200


async def test_tenant_provider_usage_routes_reject_unauthenticated(client):
    usage_resp = await client.get("/tenants/me/providers/usage")
    quota_resp = await client.get("/tenants/me/providers/quota")

    assert usage_resp.status_code == 401
    assert quota_resp.status_code == 401


async def test_check_provider_quota_available_bypasses_when_no_policy_configured() -> None:
    """No ProviderQuotaPolicyRow → result has empty decisions, not blocked."""
    # Deliberately do NOT seed any policy rows for this provider.
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        result = await check_provider_quota_available(
            session,
            tenant_id=settings.tenant_id,
            provider_id="anthropic:claude-sonnet-4-6",
            runtime_scope="judge",
            capability="judge",
            estimated_usage={"requests": 10},
        )

    assert result.blocked is False
    assert result.warning is False
    assert result.decisions == ()


async def test_tenant_provider_usage_rollup_includes_orphaned_eval_run_rows() -> None:
    """Ledger rows referencing a non-existent eval_run_id must still count toward quota.

    If the outer join on GraiEvalRunRow produces NULL (orphaned row), the
    _finalized_usage_condition OR arm for orphaned rows must include that usage.
    """
    now = datetime.now(UTC)
    # Seed a usage row with an eval_run_id that has NO corresponding GraiEvalRunRow.
    await _seed_provider_usage_row(
        provider_id="anthropic:claude-sonnet-4-6",
        tenant_id=settings.tenant_id,
        usage_key="usage_orphaned_eval",
        recorded_at=now,
        runtime_scope="judge",
        capability="judge",
        eval_run_id="gerun_orphaned_does_not_exist",
        input_tokens=77,
        output_tokens=13,
        request_count=1,
    )

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        await check_provider_quota_available(
            session,
            tenant_id=settings.tenant_id,
            provider_id="anthropic:claude-sonnet-4-6",
            runtime_scope="judge",
            capability="judge",
        )

    # result.decisions is empty (no policy rows) — but the usage must be visible
    # in the rollup. Verify by querying the usage summary directly.
    from botcheck_api.providers.usage_service import list_tenant_provider_usage_summary
    async with factory() as session:
        _, _, items = await list_tenant_provider_usage_summary(
            session, tenant_id=settings.tenant_id
        )
    anthropic_item = next(
        (item for item in items if item["provider_id"] == "anthropic:claude-sonnet-4-6"), None
    )
    assert anthropic_item is not None, "Orphaned eval ledger row was excluded from usage rollup"
    assert int(anthropic_item["input_tokens_24h"]) >= 77  # type: ignore[arg-type]


async def test_admin_provider_assignment_delete_and_reassign(client):
    create_resp = await client.post(
        "/admin/tenants/",
        json={
            "tenant_id": "acme",
            "slug": "acme",
            "display_name": "Acme Corp",
            "feature_overrides": {},
            "quota_config": {},
        },
        headers=_platform_admin_headers(),
    )
    assert create_resp.status_code == 201

    second_tenant_resp = await client.post(
        "/admin/tenants/",
        json={
            "tenant_id": "beta",
            "slug": "beta",
            "display_name": "Beta Corp",
            "feature_overrides": {},
            "quota_config": {},
        },
        headers=_platform_admin_headers(),
    )
    assert second_tenant_resp.status_code == 201

    assign_resp = await client.post(
        "/admin/providers/openai:gpt-4o-mini-tts/assign",
        json={"tenant_id": "beta"},
        headers=_platform_admin_headers(),
    )
    assert assign_resp.status_code == 200
    assert assign_resp.json()["assigned_tenant"]["tenant_id"] == "beta"

    assignments_after_assign = await client.get(
        "/admin/providers/openai:gpt-4o-mini-tts/assignments",
        headers=_platform_admin_headers(),
    )
    assert assignments_after_assign.status_code == 200
    tenant_ids_after_assign = {item["tenant_id"] for item in assignments_after_assign.json()["items"]}
    assert tenant_ids_after_assign == {"beta"}

    delete_resp = await client.delete(
        "/admin/providers/openai:gpt-4o-mini-tts/assign",
        headers=_platform_admin_headers(),
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["assigned_tenant"] is None

    reassign_resp = await client.post(
        "/admin/tenants/acme/providers/assign",
        json={"provider_id": "openai:gpt-4o-mini-tts", "is_default": True},
        headers=_platform_admin_headers(),
    )
    assert reassign_resp.status_code == 200
    assert reassign_resp.json()["enabled"] is True
    assert reassign_resp.json()["is_default"] is True

    assignments_after_create = await client.get(
        "/admin/providers/openai:gpt-4o-mini-tts/assignments",
        headers=_platform_admin_headers(),
    )
    assert assignments_after_create.status_code == 200
    assignment_rows = {
        item["tenant_id"]: item for item in assignments_after_create.json()["items"]
    }
    assert set(assignment_rows) == {"acme"}
    assert assignment_rows["acme"]["is_default"] is True

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        audit_actions = set(
            (
                await session.execute(
                    select(AuditLogRow.action).where(
                        AuditLogRow.resource_type == "tenant_provider_assignment",
                        AuditLogRow.resource_id == "openai:gpt-4o-mini-tts",
                    )
                )
            ).scalars().all()
        )
    assert "provider_assignment.deleted" in audit_actions
    assert "provider_assignment.created" in audit_actions
    assert "provider_assignment.reassigned" in audit_actions


async def test_admin_provider_quota_policy_crud_and_audits(client):
    create_resp = await client.post(
        "/admin/tenants/",
        json={
            "tenant_id": "quota-tenant",
            "slug": "quota-tenant",
            "display_name": "Quota Tenant",
            "feature_overrides": {},
            "quota_config": {},
        },
        headers=_platform_admin_headers(),
    )
    assert create_resp.status_code == 201

    assign_resp = await client.post(
        "/admin/providers/openai:gpt-4o-mini-tts/assign",
        json={"tenant_id": "quota-tenant"},
        headers=_platform_admin_headers(),
    )
    assert assign_resp.status_code == 200

    upsert_resp = await client.post(
        "/admin/providers/openai:gpt-4o-mini-tts/quota-policies",
        json={
            "tenant_id": "quota-tenant",
            "metric": "characters",
            "limit_per_day": 12000,
            "soft_limit_pct": 75,
        },
        headers=_platform_admin_headers(),
    )
    assert upsert_resp.status_code == 200
    upsert_payload = upsert_resp.json()
    assert upsert_payload["tenant_id"] == "quota-tenant"
    assert upsert_payload["provider_id"] == "openai:gpt-4o-mini-tts"
    assert upsert_payload["metric"] == "characters"
    assert upsert_payload["limit_per_day"] == 12000
    assert upsert_payload["soft_limit_pct"] == 75
    assert upsert_payload["tenant_display_name"] == "Quota Tenant"

    list_resp = await client.get(
        "/admin/providers/openai:gpt-4o-mini-tts/quota-policies",
        headers=_platform_admin_headers(),
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] >= 1
    list_items = {
        f"{item['tenant_id']}:{item['metric']}": item for item in list_resp.json()["items"]
    }
    assert list_items["quota-tenant:characters"]["limit_per_day"] == 12000

    update_resp = await client.post(
        "/admin/providers/openai:gpt-4o-mini-tts/quota-policies",
        json={
            "tenant_id": "quota-tenant",
            "metric": "characters",
            "limit_per_day": 20000,
            "soft_limit_pct": 90,
        },
        headers=_platform_admin_headers(),
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["limit_per_day"] == 20000
    assert update_resp.json()["soft_limit_pct"] == 90

    delete_resp = await client.delete(
        "/admin/providers/openai:gpt-4o-mini-tts/quota-policies/quota-tenant/characters",
        headers=_platform_admin_headers(),
    )
    assert delete_resp.status_code == 200
    assert delete_resp.json()["applied"] is True

    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        remaining = (
            await session.execute(
                select(ProviderQuotaPolicyRow).where(
                    ProviderQuotaPolicyRow.tenant_id == "quota-tenant",
                    ProviderQuotaPolicyRow.provider_id == "openai:gpt-4o-mini-tts",
                    ProviderQuotaPolicyRow.metric == "characters",
                )
            )
        ).scalar_one_or_none()
        assert remaining is None
        audit_actions = set(
            (
                await session.execute(
                    select(AuditLogRow.action).where(
                        AuditLogRow.resource_type == "provider_quota_policy",
                        AuditLogRow.resource_id == "quota-tenant:openai:gpt-4o-mini-tts:characters",
                    )
                )
            ).scalars().all()
        )
    assert "provider_quota_policy.created" in audit_actions
    assert "provider_quota_policy.updated" in audit_actions
    assert "provider_quota_policy.deleted" in audit_actions


async def test_admin_provider_quota_policy_rejects_invalid_metric(client):
    resp = await client.post(
        "/admin/providers/openai:gpt-4o-mini-tts/quota-policies",
        json={
            "tenant_id": settings.tenant_id,
            "metric": "nonsense_metric",
            "limit_per_day": 12000,
            "soft_limit_pct": 75,
        },
        headers=_platform_admin_headers(),
    )

    assert resp.status_code == 422
    assert "Unsupported provider quota metric" in resp.text


async def test_admin_provider_quota_policy_rejects_metric_incompatible_with_provider_capability(client):
    resp = await client.post(
        "/admin/providers/openai:gpt-4o-mini-tts/quota-policies",
        json={
            "tenant_id": settings.tenant_id,
            "metric": "input_tokens",
            "limit_per_day": 12000,
            "soft_limit_pct": 75,
        },
        headers=_platform_admin_headers(),
    )

    assert resp.status_code == 422
    assert "not supported for capability" in resp.text


async def test_admin_provider_quota_policy_accepts_valid_capability_metric_pair(client):
    # judge capability accepts input_tokens — confirms the new capability guard
    # still passes for a valid pair and did not accidentally tighten the allowlist.
    resp = await client.post(
        "/admin/providers/anthropic:claude-sonnet-4-6/quota-policies",
        json={
            "tenant_id": settings.tenant_id,
            "metric": "input_tokens",
            "limit_per_day": 5000,
            "soft_limit_pct": 70,
        },
        headers=_platform_admin_headers(),
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["metric"] == "input_tokens"
    assert data["limit_per_day"] == 5000

    # Cleanup
    await client.delete(
        f"/admin/providers/anthropic:claude-sonnet-4-6/quota-policies/{settings.tenant_id}/input_tokens",
        headers=_platform_admin_headers(),
    )


async def test_admin_provider_quota_policy_routes_require_platform_admin(client):
    list_resp = await client.get(
        "/admin/providers/openai:gpt-4o-mini-tts/quota-policies",
        headers=_headers("admin"),
    )
    assert list_resp.status_code == 403

    create_resp = await client.post(
        "/admin/providers/openai:gpt-4o-mini-tts/quota-policies",
        json={
            "tenant_id": settings.tenant_id,
            "metric": "characters",
            "limit_per_day": 12000,
            "soft_limit_pct": 75,
        },
        headers=_headers("admin"),
    )
    assert create_resp.status_code == 403

    delete_resp = await client.delete(
        f"/admin/providers/openai:gpt-4o-mini-tts/quota-policies/{settings.tenant_id}/characters",
        headers=_headers("admin"),
    )
    assert delete_resp.status_code == 403


# ---------------------------------------------------------------------------
# Cache-warming regression tests
#
# Three bugs caused silent cache-warming failures in 2026-04:
#   1. TTS provider seeds were missing "judge" from runtime_scopes → unsupported
#   2. parsed_voice.voice_id (AttributeError) in runtime-context when TTS unresolvable
#   3. _post_provider_circuit_state had keyword-only params but was called positionally
#
# Tests below prevent each from regressing.
# ---------------------------------------------------------------------------


async def test_internal_provider_runtime_context_tts_resolves_for_judge_scope(
    client,
    judge_auth_headers,
    monkeypatch,
):
    """TTS credentials must be returned when runtime_scope="judge".

    Regression: TTS seeds previously lacked "judge" in runtime_scopes causing
    availability_status="unsupported" and secret_fields={} for cache-worker
    requests, so no audio files were ever synthesised.
    """
    monkeypatch.setattr(settings, "openai_api_key", "")

    create_resp = await client.post(
        "/admin/providers/openai:gpt-4o-mini-tts/credentials",
        json={"secret_fields": {"api_key": "judge-scope-openai-key"}},
        headers=_platform_admin_headers(),
    )
    assert create_resp.status_code == 202

    resp = await client.post(
        "/providers/internal/runtime-context",
        json={
            "tenant_id": settings.tenant_id,
            "runtime_scope": "judge",
            "tts_voice": "openai:nova",
        },
        headers=judge_auth_headers,
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["tts"]["availability_status"] == "available"
    assert payload["tts"]["secret_fields"] == {"api_key": "judge-scope-openai-key"}
    assert payload["tts"]["credential_source"] == "db_encrypted"


async def test_internal_provider_runtime_context_returns_200_when_tts_unresolvable(
    client,
    judge_auth_headers,
):
    """Runtime-context must return 200 (not 500) when TTS provider is unresolvable.

    Regression: `parsed_voice.voice_id` (AttributeError on ParsedTTSVoice — field is
    `.voice`, not `.voice_id`) caused a 500 when resolved.get("model") was falsy
    (i.e. when the provider was unsupported/unconfigured). The `or` short-circuit
    masked it when credentials were present.

    Uses ElevenLabs, which the test fixture leaves unconfigured (elevenlabs_api_key=""
    and no seeded DB credential), so the TTS section is always non-available without
    needing to clean up state created by other tests.
    """
    resp = await client.post(
        "/providers/internal/runtime-context",
        json={
            "tenant_id": settings.tenant_id,
            "runtime_scope": "judge",
            "tts_voice": "elevenlabs:rachel",
        },
        headers=judge_auth_headers,
    )

    # Must not raise AttributeError or 500 — TTS section should be present
    # with a non-available status.
    assert resp.status_code == 200
    payload = resp.json()
    assert "tts" in payload
    assert payload["tts"]["availability_status"] != "available"
    # model field must be a non-empty string — either from the catalog or the
    # parsed_voice.voice fallback.  Before the fix this raised AttributeError
    # (`parsed_voice.voice_id` does not exist; the field is `.voice`).
    assert isinstance(payload["tts"]["model"], str) and payload["tts"]["model"]
