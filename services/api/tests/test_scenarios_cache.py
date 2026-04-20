"""Tests for /scenarios/ cache and audio preview routes."""

from unittest.mock import AsyncMock, patch

from botocore.exceptions import ClientError
from sqlalchemy import select

from botcheck_api import database
from botcheck_api.config import settings
from botcheck_api.main import app
from botcheck_api.models import TenantProviderAssignmentRow
from botcheck_api.providers.service import ensure_provider_registry_seeded
from botcheck_api.scenarios.service import ScenarioCacheInspection

from factories import (
    make_scenario_cache_sync_payload,
    make_scenario_upload_payload,
    make_scenario_yaml,
    make_turn,
)
from scenarios_test_helpers import _viewer_auth_headers, store_scenario_yaml_direct


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


class TestScenarioCacheRebuild:
    async def test_rebuild_requires_auth(self, client, uploaded_scenario):
        resp = await client.post(f"/scenarios/{uploaded_scenario['id']}/cache/rebuild")
        assert resp.status_code == 401

    async def test_rebuild_not_found_returns_404(self, client, user_auth_headers):
        resp = await client.post(
            "/scenarios/does-not-exist/cache/rebuild",
            headers=user_auth_headers,
        )
        assert resp.status_code == 404

    async def test_rebuild_returns_503_when_cache_feature_disabled(
        self, client, uploaded_scenario, user_auth_headers, monkeypatch
    ):
        monkeypatch.setattr(settings, "tts_cache_enabled", False)
        resp = await client.post(
            f"/scenarios/{uploaded_scenario['id']}/cache/rebuild",
            headers=user_auth_headers,
        )
        assert resp.status_code == 503

    async def test_rebuild_enqueues_job_and_sets_warming_status(
        self, client, uploaded_scenario, user_auth_headers
    ):
        enqueue_mock = app.state.arq_cache_pool.enqueue_job
        enqueue_mock.reset_mock()

        resp = await client.post(
            f"/scenarios/{uploaded_scenario['id']}/cache/rebuild",
            headers=user_auth_headers,
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["scenario_id"] == uploaded_scenario["id"]
        assert data["cache_status"] == "warming"
        assert data["queue"] == "arq:cache"
        assert data["enqueued"] is True

        enqueue_mock.assert_awaited_once()
        _, kwargs = enqueue_mock.await_args
        assert kwargs["_queue_name"] == "arq:cache"
        assert kwargs["payload"]["scenario_id"] == uploaded_scenario["id"]
        assert kwargs["payload"]["tenant_id"] == settings.tenant_id
        assert kwargs["payload"]["scenario_version_hash"]
        assert kwargs["payload"]["scenario_payload"]["id"] == uploaded_scenario["id"]
        assert len(kwargs["payload"]["scenario_payload"]["turns"]) == 2

        list_resp = await client.get("/scenarios/", headers=user_auth_headers)
        assert list_resp.status_code == 200
        assert list_resp.json()[0]["cache_status"] == "warming"

    async def test_rebuild_returns_503_when_queue_unavailable_and_rolls_back_status(
        self, client, uploaded_scenario, user_auth_headers
    ):
        original_cache_pool = app.state.arq_cache_pool
        original_pool = app.state.arq_pool
        app.state.arq_cache_pool = None
        try:
            resp = await client.post(
                f"/scenarios/{uploaded_scenario['id']}/cache/rebuild",
                headers=user_auth_headers,
            )
            assert resp.status_code == 503
        finally:
            app.state.arq_cache_pool = original_cache_pool
            app.state.arq_pool = original_pool

        list_resp = await client.get("/scenarios/", headers=user_auth_headers)
        assert list_resp.status_code == 200
        assert list_resp.json()[0]["cache_status"] == "warming"

class TestScenarioCacheSync:
    async def test_sync_returns_503_when_cache_feature_disabled(
        self, client, uploaded_scenario, judge_auth_headers, monkeypatch
    ):
        monkeypatch.setattr(settings, "tts_cache_enabled", False)
        resp = await client.post(
            f"/scenarios/{uploaded_scenario['id']}/cache/sync",
            headers=judge_auth_headers,
            json=make_scenario_cache_sync_payload(
                uploaded_scenario["version_hash"],
                cache_status="warm",
            ),
        )
        assert resp.status_code == 503

    async def test_sync_requires_service_token(self, client, uploaded_scenario, user_auth_headers):
        resp = await client.post(
            f"/scenarios/{uploaded_scenario['id']}/cache/sync",
            headers=user_auth_headers,
            json=make_scenario_cache_sync_payload(
                uploaded_scenario["version_hash"],
                cache_status="warm",
            ),
        )
        assert resp.status_code == 401

    async def test_sync_rejects_non_judge_service_token(
        self, client, uploaded_scenario, harness_auth_headers
    ):
        resp = await client.post(
            f"/scenarios/{uploaded_scenario['id']}/cache/sync",
            headers=harness_auth_headers,
            json=make_scenario_cache_sync_payload(
                uploaded_scenario["version_hash"],
                cache_status="warm",
            ),
        )
        assert resp.status_code == 403

    async def test_sync_rejects_warming_status_from_worker(
        self, client, uploaded_scenario, judge_auth_headers
    ):
        resp = await client.post(
            f"/scenarios/{uploaded_scenario['id']}/cache/sync",
            headers=judge_auth_headers,
            json=make_scenario_cache_sync_payload(
                uploaded_scenario["version_hash"],
                cache_status="warming",
            ),
        )
        assert resp.status_code == 422

    async def test_sync_applies_when_version_matches(
        self, client, uploaded_scenario, judge_auth_headers, user_auth_headers
    ):
        resp = await client.post(
            f"/scenarios/{uploaded_scenario['id']}/cache/sync",
            headers=judge_auth_headers,
            json=make_scenario_cache_sync_payload(
                uploaded_scenario["version_hash"],
                cache_status="warm",
                cached_turns=2,
                skipped_turns=0,
                failed_turns=0,
                manifest_s3_key=f"{settings.tenant_id}/tts-cache/{uploaded_scenario['id']}/manifest.json",
            ),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["applied"] is True
        assert data["reason"] == "applied"
        assert data["cache_status"] == "warm"

        listed = await client.get("/scenarios/", headers=user_auth_headers)
        assert listed.status_code == 200
        assert listed.json()[0]["cache_status"] == "warm"

    async def test_sync_ignores_stale_version(
        self, client, uploaded_scenario, judge_auth_headers, user_auth_headers
    ):
        resp = await client.post(
            f"/scenarios/{uploaded_scenario['id']}/cache/sync",
            headers=judge_auth_headers,
            json=make_scenario_cache_sync_payload(
                "stale-version",
                cache_status="warm",
            ),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["applied"] is False
        assert data["reason"] == "version_mismatch"
        assert data["cache_status"] == "warming"

        listed = await client.get("/scenarios/", headers=user_auth_headers)
        assert listed.status_code == 200
        assert listed.json()[0]["cache_status"] == "warming"

class TestScenarioCacheState:
    async def test_cache_state_requires_auth(self, client, uploaded_scenario):
        resp = await client.get(f"/scenarios/{uploaded_scenario['id']}/cache/state")
        assert resp.status_code == 401

    async def test_cache_state_returns_503_when_feature_disabled(
        self, client, uploaded_scenario, user_auth_headers, monkeypatch
    ):
        monkeypatch.setattr(settings, "tts_cache_enabled", False)
        resp = await client.get(
            f"/scenarios/{uploaded_scenario['id']}/cache/state",
            headers=user_auth_headers,
        )
        assert resp.status_code == 503

    async def test_cache_state_returns_manifest_and_turn_states(
        self, client, uploaded_scenario, user_auth_headers, monkeypatch
    ):
        monkeypatch.setattr(
            "botcheck_api.scenarios.cache_routes.inspect_scenario_tts_cache",
            AsyncMock(
                return_value=ScenarioCacheInspection(
                    cache_status="partial",
                    cached_turns=1,
                    failed_turns=1,
                    total_harness_turns=2,
                    manifest_present=True,
                    turn_states=[
                        {
                            "turn_id": "t1",
                            "status": "cached",
                            "key": f"{settings.tenant_id}/tts-cache/t1/hash.wav",
                        },
                        {
                            "turn_id": "t2",
                            "status": "failed",
                            "key": f"{settings.tenant_id}/tts-cache/t2/hash.wav",
                        },
                    ],
                )
            ),
        )

        resp = await client.get(
            f"/scenarios/{uploaded_scenario['id']}/cache/state",
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["cache_status"] == "partial"
        assert data["cached_turns"] == 1
        assert data["failed_turns"] == 1
        assert data["total_harness_turns"] == 2
        assert data["bucket_name"] == settings.s3_bucket_prefix
        assert len(data["turn_states"]) == 2
        assert {row["turn_id"] for row in data["turn_states"]} == {"t1", "t2"}

    async def test_cache_state_falls_back_to_object_verification_when_manifest_missing(
        self, client, uploaded_scenario, user_auth_headers, monkeypatch
    ):
        monkeypatch.setattr(
            "botcheck_api.scenarios.cache_routes.inspect_scenario_tts_cache",
            AsyncMock(
                return_value=ScenarioCacheInspection(
                    cache_status="cold",
                    cached_turns=0,
                    failed_turns=2,
                    total_harness_turns=2,
                    manifest_present=False,
                    turn_states=[
                        {
                            "turn_id": "t1",
                            "status": "failed",
                            "key": f"{settings.tenant_id}/tts-cache/t1/missing.wav",
                        },
                        {
                            "turn_id": "t2",
                            "status": "failed",
                            "key": f"{settings.tenant_id}/tts-cache/t2/missing.wav",
                        },
                    ],
                )
            ),
        )

        resp = await client.get(
            f"/scenarios/{uploaded_scenario['id']}/cache/state",
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["cache_status"] == "cold"
        assert data["failed_turns"] == 2

class TestScenarioAudioPreview:
    async def test_preview_requires_auth(self, client, uploaded_scenario):
        resp = await client.get(f"/scenarios/{uploaded_scenario['id']}/turns/t1/audio")
        assert resp.status_code == 401

    async def test_preview_returns_503_when_feature_disabled(
        self, client, uploaded_scenario, user_auth_headers, monkeypatch
    ):
        monkeypatch.setattr(settings, "tts_cache_enabled", False)
        resp = await client.get(
            f"/scenarios/{uploaded_scenario['id']}/turns/t1/audio",
            headers=user_auth_headers,
        )
        assert resp.status_code == 503

    async def test_preview_requires_admin_or_qa_role(self, client, uploaded_scenario):
        resp = await client.get(
            f"/scenarios/{uploaded_scenario['id']}/turns/t1/audio",
            headers=_viewer_auth_headers(),
        )
        assert resp.status_code == 403

    async def test_preview_rate_limited_returns_429(
        self, client, uploaded_scenario, user_auth_headers, monkeypatch
    ):
        monkeypatch.setattr(
            "botcheck_api.scenarios.cache_routes.check_login_rate_limit",
            lambda **_kwargs: (False, 7),
        )
        resp = await client.get(
            f"/scenarios/{uploaded_scenario['id']}/turns/t1/audio",
            headers=user_auth_headers,
        )
        assert resp.status_code == 429
        assert resp.json()["error_code"] == "preview_rate_limited"
        assert resp.headers.get("Retry-After") == "7"

    async def test_preview_cache_hit_streams_cached_wav(
        self, client, uploaded_scenario, user_auth_headers, monkeypatch
    ):
        download_mock = AsyncMock(return_value=(b"RIFF...WAVE", "audio/wav"))
        synth_mock = AsyncMock(return_value=b"SHOULD_NOT_BE_USED")
        upload_mock = AsyncMock(return_value=None)
        monkeypatch.setattr("botcheck_api.scenarios.cache_routes.download_artifact_bytes", download_mock)
        monkeypatch.setattr("botcheck_api.scenarios.cache_routes.synthesize_preview_wav", synth_mock)
        monkeypatch.setattr("botcheck_api.scenarios.cache_routes.upload_artifact_bytes", upload_mock)

        resp = await client.get(
            f"/scenarios/{uploaded_scenario['id']}/turns/t1/audio",
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("audio/wav")
        assert resp.content == b"RIFF...WAVE"
        synth_mock.assert_not_awaited()
        upload_mock.assert_not_awaited()

    async def test_preview_cache_miss_synthesizes_and_uploads(
        self, client, uploaded_scenario, user_auth_headers, monkeypatch
    ):
        miss_exc = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        download_mock = AsyncMock(side_effect=miss_exc)
        synth_mock = AsyncMock(return_value=b"RIFF_MISS")
        upload_mock = AsyncMock(return_value=None)
        monkeypatch.setattr("botcheck_api.scenarios.cache_routes.download_artifact_bytes", download_mock)
        monkeypatch.setattr("botcheck_api.scenarios.cache_routes.synthesize_preview_wav", synth_mock)
        monkeypatch.setattr("botcheck_api.scenarios.cache_routes.upload_artifact_bytes", upload_mock)

        resp = await client.get(
            f"/scenarios/{uploaded_scenario['id']}/turns/t1/audio",
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("audio/wav")
        assert resp.content == b"RIFF_MISS"
        synth_mock.assert_awaited_once()
        upload_mock.assert_awaited_once()

    async def test_preview_turn_not_found_returns_404(
        self, client, uploaded_scenario, user_auth_headers
    ):
        resp = await client.get(
            f"/scenarios/{uploaded_scenario['id']}/turns/does-not-exist/audio",
            headers=user_auth_headers,
        )
        assert resp.status_code == 404

    async def test_preview_rejects_bot_turn_with_422(
        self, client, user_auth_headers
    ):
        scenario_with_bot_turn = make_scenario_yaml(
            scenario_id="preview-bot-turn",
            name="Preview Bot Turn",
            scenario_type="golden_path",
            turns=[
                make_turn(turn_id="t1", speaker="harness", text="Hello"),
                make_turn(
                    turn_id="t_bot",
                    speaker="bot",
                    text="Hi there",
                    wait_for_response=False,
                ),
            ],
        )
        create_resp = await client.post(
            "/scenarios/",
            json=make_scenario_upload_payload(scenario_with_bot_turn),
            headers=user_auth_headers,
        )
        assert create_resp.status_code == 201

        resp = await client.get(
            "/scenarios/preview-bot-turn/turns/t_bot/audio",
            headers=user_auth_headers,
        )
        assert resp.status_code == 422
        assert "harness turn" in resp.json()["detail"]

    async def test_preview_synthesis_failure_returns_503(
        self, client, uploaded_scenario, user_auth_headers, monkeypatch
    ):
        miss_exc = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        monkeypatch.setattr(
            "botcheck_api.scenarios.cache_routes.download_artifact_bytes",
            AsyncMock(side_effect=miss_exc),
        )
        monkeypatch.setattr(
            "botcheck_api.scenarios.cache_routes.synthesize_preview_wav",
            AsyncMock(side_effect=Exception("openai timeout")),
        )

        resp = await client.get(
            f"/scenarios/{uploaded_scenario['id']}/turns/t1/audio",
            headers=user_auth_headers,
        )
        assert resp.status_code == 503

    async def test_preview_upload_failure_still_returns_audio(
        self, client, uploaded_scenario, user_auth_headers, monkeypatch
    ):
        miss_exc = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        monkeypatch.setattr(
            "botcheck_api.scenarios.cache_routes.download_artifact_bytes",
            AsyncMock(side_effect=miss_exc),
        )
        monkeypatch.setattr(
            "botcheck_api.scenarios.cache_routes.synthesize_preview_wav",
            AsyncMock(return_value=b"RIFF_SYNTH"),
        )
        monkeypatch.setattr(
            "botcheck_api.scenarios.cache_routes.upload_artifact_bytes",
            AsyncMock(side_effect=Exception("S3 write failed")),
        )

        resp = await client.get(
            f"/scenarios/{uploaded_scenario['id']}/turns/t1/audio",
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.content == b"RIFF_SYNTH"

    async def test_preview_non_404_s3_error_returns_503(
        self, client, uploaded_scenario, user_auth_headers, monkeypatch
    ):
        s3_error = ClientError({"Error": {"Code": "InternalError"}}, "GetObject")
        monkeypatch.setattr(
            "botcheck_api.scenarios.cache_routes.download_artifact_bytes",
            AsyncMock(side_effect=s3_error),
        )

        resp = await client.get(
            f"/scenarios/{uploaded_scenario['id']}/turns/t1/audio",
            headers=user_auth_headers,
        )
        assert resp.status_code == 503

    async def test_preview_unsupported_provider_returns_error_code(
        self, client, user_auth_headers, monkeypatch
    ):
        scenario_with_unsupported_provider = make_scenario_yaml(
            scenario_id="preview-unsupported-provider",
            name="Preview Unsupported Provider",
            scenario_type="golden_path",
            turns=[make_turn(turn_id="t1", speaker="harness", text="Hello")],
            overrides={"config": {"tts_voice": "deepgram:aura-asteria-en"}},
        )
        await store_scenario_yaml_direct(scenario_with_unsupported_provider)

        monkeypatch.setattr(
            "botcheck_api.scenarios.cache_routes.download_artifact_bytes",
            AsyncMock(side_effect=ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")),
        )

        resp = await client.get(
            "/scenarios/preview-unsupported-provider/turns/t1/audio",
            headers=user_auth_headers,
        )
        assert resp.status_code == 503
        assert resp.json()["error_code"] == "tts_provider_unsupported"

    async def test_preview_disabled_elevenlabs_provider_returns_error_code(
        self, client, user_auth_headers, monkeypatch
    ):
        scenario_with_disabled_provider = make_scenario_yaml(
            scenario_id="preview-disabled-elevenlabs",
            name="Preview Disabled ElevenLabs",
            scenario_type="golden_path",
            turns=[make_turn(turn_id="t1", speaker="harness", text="Hello")],
            overrides={"config": {"tts_voice": "elevenlabs:voice-123"}},
        )
        await store_scenario_yaml_direct(scenario_with_disabled_provider)
        monkeypatch.setattr(settings, "feature_tts_provider_elevenlabs_enabled", False)
        monkeypatch.setattr(
            "botcheck_api.scenarios.cache_routes.download_artifact_bytes",
            AsyncMock(side_effect=ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")),
        )

        resp = await client.get(
            "/scenarios/preview-disabled-elevenlabs/turns/t1/audio",
            headers=user_auth_headers,
        )

        assert resp.status_code == 503
        assert resp.json()["error_code"] == "tts_provider_disabled"

    async def test_preview_tenant_disabled_openai_provider_returns_error_code(
        self, client, uploaded_scenario, user_auth_headers, monkeypatch
    ):
        await _set_provider_assignment_enabled(
            tenant_id=settings.tenant_id,
            provider_id="openai:gpt-4o-mini-tts",
            enabled=False,
        )
        monkeypatch.setattr(
            "botcheck_api.scenarios.cache_routes.download_artifact_bytes",
            AsyncMock(side_effect=ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")),
        )

        resp = await client.get(
            f"/scenarios/{uploaded_scenario['id']}/turns/t1/audio",
            headers=user_auth_headers,
        )

        assert resp.status_code == 503
        assert resp.json()["error_code"] == "tts_provider_disabled"
