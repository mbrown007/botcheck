"""Tests for /scenarios/ validation route."""

import yaml

from sqlalchemy import select

from botcheck_api import database
from botcheck_api.admin.service_providers import delete_platform_provider_credential
from botcheck_api.config import settings
from botcheck_api.models import ProviderCredentialRow, TenantProviderAssignmentRow
from botcheck_api.providers.service import ensure_provider_registry_seeded

from factories import make_scenario_upload_payload, make_scenario_yaml, make_turn


def _time_route_scenario_yaml(*, scenario_id: str = "validate-time-route") -> str:
    return yaml.safe_dump(
        {
            "version": "1.0",
            "id": scenario_id,
            "name": "Time Route Validation",
            "type": "reliability",
            "bot": {
                "endpoint": "sip:bot@test.example.com",
                "protocol": "sip",
            },
            "turns": [
                {
                    "id": "t0_pickup",
                    "kind": "bot_listen",
                    "next": "t_route",
                },
                {
                    "id": "t_route",
                    "kind": "time_route",
                    "timezone": "UTC",
                    "windows": [
                        {
                            "label": "business_hours",
                            "start": "09:00",
                            "end": "17:00",
                            "next": "t_hours",
                        },
                        {
                            "label": "after_hours",
                            "start": "17:00",
                            "end": "09:00",
                            "next": "t_after",
                        },
                    ],
                    "default": "t_default",
                },
                {
                    "id": "t_hours",
                    "kind": "harness_prompt",
                    "content": {"text": "Business hours greeting"},
                    "listen": False,
                    "next": "t_end",
                },
                {
                    "id": "t_after",
                    "kind": "harness_prompt",
                    "content": {"text": "After hours greeting"},
                    "listen": False,
                    "next": "t_end",
                },
                {
                    "id": "t_default",
                    "kind": "harness_prompt",
                    "content": {"text": "Default greeting"},
                    "listen": False,
                    "next": "t_end",
                },
                {"id": "t_end", "kind": "hangup"},
            ],
        },
        sort_keys=False,
    )


async def _delete_platform_provider_credential(*, provider_id: str) -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        existing = (
            await session.execute(
                select(ProviderCredentialRow).where(
                    ProviderCredentialRow.provider_id == provider_id,
                    ProviderCredentialRow.owner_scope == "platform",
                    ProviderCredentialRow.tenant_id.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            await delete_platform_provider_credential(
                session,
                provider_id=provider_id,
                actor_id="test-fixture",
                actor_tenant_id=settings.tenant_id,
            )
            await session.commit()


async def _set_provider_assignment_enabled(*, tenant_id: str, provider_id: str, enabled: bool) -> None:
    factory = database.AsyncSessionLocal
    assert factory is not None
    async with factory() as session:
        await ensure_provider_registry_seeded(session, tenant_ids=[tenant_id])
        row = (
            await session.execute(
                select(TenantProviderAssignmentRow).where(
                    TenantProviderAssignmentRow.tenant_id == tenant_id,
                    TenantProviderAssignmentRow.provider_id == provider_id,
                )
            )
        ).scalar_one()
        row.enabled = enabled
        await session.commit()


class TestValidateScenario:
    async def test_valid_scenario(self, client, scenario_yaml, user_auth_headers):
        resp = await client.post(
            "/scenarios/validate",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["errors"] == []
        assert data["warnings"] == []
        assert data["scenario_id"] == "test-jailbreak"
        assert data["turns"] == 2
        assert data["path_summary"] is not None
        assert "[01] t1" in data["path_summary"]
        assert "-> t2 (implicit)" in data["path_summary"]

    async def test_invalid_scenario(self, client, user_auth_headers):
        resp = await client.post(
            "/scenarios/validate",
            json=make_scenario_upload_payload("this is not a scenario"),
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert len(data["errors"]) >= 1
        assert data["errors"][0]["field"] == "$"

    async def test_validate_does_not_persist(self, client, scenario_yaml, user_auth_headers):
        """Validation must not store the scenario."""
        await client.post(
            "/scenarios/validate",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )
        list_resp = await client.get("/scenarios/", headers=user_auth_headers)
        assert list_resp.json() == []

    async def test_validate_requires_auth(self, client, scenario_yaml):
        resp = await client.post(
            "/scenarios/validate",
            json=make_scenario_upload_payload(scenario_yaml),
        )
        assert resp.status_code == 401

    async def test_validate_emits_cycle_guaranteed_loop_warning(
        self, client, user_auth_headers
    ):
        cycle_yaml = make_scenario_yaml(
            scenario_id="cycle-guaranteed",
            name="Cycle Guaranteed",
            turns=[
                make_turn(
                    turn_id="t1",
                    text="Turn 1",
                    next="t2",
                    max_visits=1,
                ),
                make_turn(
                    turn_id="t2",
                    text="Turn 2",
                    next="t1",
                    max_visits=1,
                ),
            ],
        )
        resp = await client.post(
            "/scenarios/validate",
            json=make_scenario_upload_payload(cycle_yaml),
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["errors"] == []
        warnings = data["warnings"]
        assert len(warnings) == 1
        assert warnings[0]["code"] == "CYCLE_GUARANTEED_LOOP"
        assert warnings[0]["turn_ids"] == ["t1", "t2"]
        assert "? default" not in data["path_summary"]

    async def test_validate_emits_cycle_unlimited_visit_warning(
        self, client, user_auth_headers
    ):
        cycle_yaml = make_scenario_yaml(
            scenario_id="cycle-unlimited",
            name="Cycle Unlimited",
            turns=[
                make_turn(
                    turn_id="t1",
                    text="Loop",
                    next="t1",
                    max_visits=0,
                )
            ],
        )
        resp = await client.post(
            "/scenarios/validate",
            json=make_scenario_upload_payload(cycle_yaml),
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["errors"] == []
        warnings = data["warnings"]
        assert len(warnings) == 1
        assert warnings[0]["code"] == "CYCLE_UNLIMITED_VISIT"
        assert warnings[0]["turn_ids"] == ["t1"]
        assert "max_visits=∞" in data["path_summary"]

    async def test_validate_includes_branching_ascii_path_summary(
        self, client, user_auth_headers
    ):
        branching_yaml = make_scenario_yaml(
            scenario_id="branch-demo",
            name="Branch Demo",
            turns=[
                make_turn(
                    turn_id="t1",
                    text="route me",
                    branching={
                        "cases": [
                            {"condition": "billing", "next": "t2_billing"},
                            {"condition": "technical", "next": "t2_technical"},
                        ],
                        "default": "t2_fallback",
                    },
                ),
                make_turn(turn_id="t2_billing", text="billing follow-up"),
                make_turn(turn_id="t2_technical", text="technical follow-up"),
                make_turn(turn_id="t2_fallback", text="fallback follow-up"),
            ],
        )
        resp = await client.post(
            "/scenarios/validate",
            json=make_scenario_upload_payload(branching_yaml),
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        summary = data["path_summary"]
        assert summary is not None
        assert "? billing -> t2_billing" in summary
        assert "? technical -> t2_technical" in summary
        assert "? default -> t2_fallback" in summary

    async def test_validate_accepts_time_route_scenario(
        self, client, user_auth_headers
    ):
        resp = await client.post(
            "/scenarios/validate",
            json=make_scenario_upload_payload(_time_route_scenario_yaml()),
            headers=user_auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["errors"] == []
        assert data["warnings"] == []
        assert data["scenario_id"] == "validate-time-route"
        # 6 turns: t0_pickup, t_route, t_hours, t_after, t_default, t_end
        assert data["turns"] == 6
        # ascii_path_summary renders turn ids and kinds via implicit-next fallthrough;
        # time_route window arms are NOT expanded — only the node itself appears
        summary = data["path_summary"]
        assert summary is not None
        assert "t0_pickup" in summary
        assert "t_route [time_route]" in summary
        assert "t_hours [harness_prompt]" in summary
        assert "t_after [harness_prompt]" in summary
        assert "t_default [harness_prompt]" in summary

    async def test_validate_rejects_time_route_with_bad_hhmm_format(
        self, client, user_auth_headers
    ):
        import yaml as _yaml

        bad_yaml = _yaml.safe_dump(
            {
                "version": "1.0",
                "id": "validate-bad-hhmm",
                "name": "Bad HHMM",
                "type": "reliability",
                "bot": {"endpoint": "sip:bot@test.example.com", "protocol": "sip"},
                "turns": [
                    {
                        "id": "t_route",
                        "kind": "time_route",
                        "timezone": "UTC",
                        "windows": [
                            {
                                "label": "biz",
                                "start": "9:00",
                                "end": "17:00",
                                "next": "t_end",
                            }
                        ],
                        "default": "t_end",
                    },
                    {"id": "t_end", "kind": "hangup"},
                ],
            },
            sort_keys=False,
        )

        resp = await client.post(
            "/scenarios/validate",
            json=make_scenario_upload_payload(bad_yaml),
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert any("windows" in e["field"] for e in data["errors"])

    async def test_validate_rejects_time_route_with_invalid_timezone(
        self, client, user_auth_headers
    ):
        import yaml as _yaml

        bad_yaml = _yaml.safe_dump(
            {
                "version": "1.0",
                "id": "validate-bad-tz",
                "name": "Bad TZ",
                "type": "reliability",
                "bot": {"endpoint": "sip:bot@test.example.com", "protocol": "sip"},
                "turns": [
                    {
                        "id": "t_route",
                        "kind": "time_route",
                        "timezone": "Not/AReal/Timezone",
                        "windows": [
                            {
                                "label": "biz",
                                "start": "09:00",
                                "end": "17:00",
                                "next": "t_end",
                            }
                        ],
                        "default": "t_end",
                    },
                    {"id": "t_end", "kind": "hangup"},
                ],
            },
            sort_keys=False,
        )

        resp = await client.post(
            "/scenarios/validate",
            json=make_scenario_upload_payload(bad_yaml),
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert any("time_route" in e["field"] for e in data["errors"])
        assert any("timezone" in e["message"].lower() for e in data["errors"])

    async def test_validate_reports_disabled_tts_provider_without_persisting(
        self, client, user_auth_headers, monkeypatch
    ):
        from botcheck_api.config import settings

        monkeypatch.setattr(settings, "feature_tts_provider_elevenlabs_enabled", False)
        scenario_yaml = make_scenario_yaml(
            scenario_id="validate-disabled-provider",
            overrides={"config": {"tts_voice": "elevenlabs:voice-123"}},
        )

        resp = await client.post(
            "/scenarios/validate",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["valid"] is False
        assert payload["errors"] == [
            {
                "field": "config.tts_voice",
                "message": "TTS provider disabled: elevenlabs",
            }
        ]

    async def test_validate_reports_tenant_disabled_tts_provider_without_persisting(
        self, client, user_auth_headers
    ):
        await _set_provider_assignment_enabled(
            tenant_id=settings.tenant_id,
            provider_id="openai:gpt-4o-mini-tts",
            enabled=False,
        )
        scenario_yaml = make_scenario_yaml(
            scenario_id="validate-tenant-disabled-provider",
            overrides={"config": {"tts_voice": "openai:alloy"}},
        )

        resp = await client.post(
            "/scenarios/validate",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["valid"] is False
        assert payload["errors"] == [
            {
                "field": "config.tts_voice",
                "message": "TTS provider disabled: openai",
            }
        ]

    async def test_validate_reports_unsupported_stt_provider_without_persisting(
        self, client, user_auth_headers
    ):
        scenario_yaml = make_scenario_yaml(
            scenario_id="validate-unsupported-stt-provider",
            overrides={
                "config": {
                    "stt_provider": "whisper",
                    "stt_model": "whisper-1",
                }
            },
        )

        resp = await client.post(
            "/scenarios/validate",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["valid"] is False
        assert payload["errors"] == [
            {
                "field": "config.stt_provider",
                "message": "STT provider currently unsupported: whisper",
            }
        ]

    async def test_validate_reports_disabled_stt_provider_without_persisting(
        self, client, user_auth_headers, monkeypatch
    ):
        monkeypatch.setattr(settings, "feature_stt_provider_deepgram_enabled", False)
        scenario_yaml = make_scenario_yaml(
            scenario_id="validate-disabled-stt-provider",
            overrides={
                "config": {
                    "stt_provider": "deepgram",
                    "stt_model": "nova-2-phonecall",
                }
            },
        )

        resp = await client.post(
            "/scenarios/validate",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["valid"] is False
        assert payload["errors"] == [
            {
                "field": "config.stt_provider",
                "message": "STT provider disabled: deepgram",
            }
        ]

    async def test_validate_reports_unconfigured_azure_stt_provider_without_persisting(
        self, client, user_auth_headers, monkeypatch
    ):
        monkeypatch.setattr(settings, "feature_stt_provider_azure_enabled", True)
        await _delete_platform_provider_credential(provider_id="azure:azure-speech")
        scenario_yaml = make_scenario_yaml(
            scenario_id="validate-unconfigured-azure-stt-provider",
            overrides={
                "config": {
                    "stt_provider": "azure",
                    "stt_model": "azure-default",
                }
            },
        )

        resp = await client.post(
            "/scenarios/validate",
            json=make_scenario_upload_payload(scenario_yaml),
            headers=user_auth_headers,
        )

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["valid"] is False
        assert payload["errors"] == [
            {
                "field": "config.stt_provider",
                "message": "STT provider not configured: azure",
            }
        ]
