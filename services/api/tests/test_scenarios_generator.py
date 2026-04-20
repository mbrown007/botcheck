"""Tests for /scenarios/generate route."""

import json
from unittest.mock import AsyncMock, patch

from botcheck_api.config import settings
from botcheck_api.main import app

from factories import make_scenario_generate_payload

class TestGenerateScenarios:
    """Tests for POST /scenarios/generate and GET /scenarios/generate/{job_id}."""

    async def test_generate_returns_202_with_job_id(self, client, user_auth_headers):
        resp = await client.post(
            "/scenarios/generate",
            json=make_scenario_generate_payload(
                target_system_prompt="You are a customer service bot.",
                user_objective="Test jailbreak resistance",
                count=2,
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "job_id" in data
        assert len(data["job_id"]) > 0

    async def test_generate_enqueues_to_judge_queue(self, client, user_auth_headers):
        enqueue_mock = app.state.arq_pool.enqueue_job
        enqueue_mock.reset_mock()

        resp = await client.post(
            "/scenarios/generate",
            json=make_scenario_generate_payload(
                target_system_prompt="You are a customer service bot.",
                user_objective="Test adversarial resistance",
                count=3,
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 202

        enqueue_mock.assert_awaited_once()
        args, kwargs = enqueue_mock.await_args
        assert args[0] == "generate_scenarios"
        assert kwargs["_queue_name"] == "arq:judge"
        payload = kwargs["payload"]
        assert payload["count"] == 3
        assert payload["tenant_id"] == settings.tenant_id
        assert "target_system_prompt" in payload
        assert "user_objective" in payload

    async def test_generate_stores_pending_state_in_redis(self, client, user_auth_headers):
        set_mock = app.state.arq_pool.set
        set_mock.reset_mock()

        resp = await client.post(
            "/scenarios/generate",
            json=make_scenario_generate_payload(
                target_system_prompt="You are a bot.",
                user_objective="Find weaknesses",
                count=1,
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        set_mock.assert_awaited_once()
        key, json_blob = set_mock.await_args[0]
        assert f"botcheck:generate:{job_id}" == key
        state = json.loads(json_blob)
        assert state["status"] == "pending"
        assert state["count_requested"] == 1
        assert state["job_id"] == job_id

    async def test_generate_requires_auth(self, client):
        resp = await client.post(
            "/scenarios/generate",
            json=make_scenario_generate_payload(
                target_system_prompt="You are a bot.",
                user_objective="Test",
                count=1,
            ),
        )
        assert resp.status_code == 401

    async def test_generate_rejects_invalid_count_zero(self, client, user_auth_headers):
        resp = await client.post(
            "/scenarios/generate",
            json=make_scenario_generate_payload(
                target_system_prompt="You are a bot.",
                user_objective="Test",
                count=0,
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 422

    async def test_generate_rejects_invalid_count_eleven(self, client, user_auth_headers):
        resp = await client.post(
            "/scenarios/generate",
            json=make_scenario_generate_payload(
                target_system_prompt="You are a bot.",
                user_objective="Test",
                count=11,
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 422

    async def test_generate_rejects_prompt_too_long(self, client, user_auth_headers):
        resp = await client.post(
            "/scenarios/generate",
            json=make_scenario_generate_payload(
                target_system_prompt="x" * 8001,
                user_objective="Test",
                count=1,
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 422

    async def test_generate_rate_limited_returns_429(
        self, client, user_auth_headers, monkeypatch
    ):
        monkeypatch.setattr(
            "botcheck_api.scenarios.generate_routes.check_login_rate_limit",
            lambda **_kwargs: (False, 60),
        )
        resp = await client.post(
            "/scenarios/generate",
            json=make_scenario_generate_payload(
                target_system_prompt="You are a bot.",
                user_objective="Test",
                count=1,
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 429
        assert resp.json()["error_code"] == "generate_rate_limited"
        assert resp.headers.get("Retry-After") == "60"

    async def test_get_job_returns_404_for_unknown(self, client, user_auth_headers):
        # mock_pool.get returns None by default → 404
        resp = await client.get(
            "/scenarios/generate/nonexistent-job-id",
            headers=user_auth_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "job_not_found"

    async def test_get_job_returns_state_from_redis(self, client, user_auth_headers):
        job_state = {
            "job_id": "test-job-123",
            "status": "complete",
            "count_requested": 2,
            "count_succeeded": 2,
            "scenarios": [
                {
                    "yaml": "version: '1.0'\nid: test\nname: Test",
                    "name": "Test Scenario",
                    "type": "adversarial",
                    "technique": "dan_prompt",
                    "turns": 2,
                }
            ],
            "errors": [],
            "created_at": "2026-03-02T00:00:00+00:00",
            "completed_at": "2026-03-02T00:00:20+00:00",
        }
        app.state.arq_pool.get.return_value = json.dumps(job_state).encode()

        resp = await client.get(
            "/scenarios/generate/test-job-123",
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "test-job-123"
        assert data["status"] == "complete"
        assert data["count_succeeded"] == 2
        assert len(data["scenarios"]) == 1
        assert data["scenarios"][0]["technique"] == "dan_prompt"

        # Reset so other tests get None
        app.state.arq_pool.get.return_value = None

    async def test_get_job_requires_auth(self, client):
        resp = await client.get("/scenarios/generate/some-job")
        assert resp.status_code == 401

    async def test_generate_503_when_no_pool(self, client, user_auth_headers):
        app.state.arq_pool = None
        try:
            resp = await client.post(
                "/scenarios/generate",
                json=make_scenario_generate_payload(
                    target_system_prompt="You are a bot.",
                    user_objective="Test",
                    count=1,
                ),
                headers=user_auth_headers,
            )
            assert resp.status_code == 503
        finally:
            from unittest.mock import AsyncMock, MagicMock
            mock_pool = MagicMock()
            mock_pool.enqueue_job = AsyncMock()
            mock_pool.set = AsyncMock()
            mock_pool.get = AsyncMock(return_value=None)
            app.state.arq_pool = mock_pool

    async def test_get_job_503_when_no_pool(self, client, user_auth_headers):
        app.state.arq_pool = None
        try:
            resp = await client.get(
                "/scenarios/generate/some-job-id",
                headers=user_auth_headers,
            )
            assert resp.status_code == 503
        finally:
            from unittest.mock import AsyncMock, MagicMock
            mock_pool = MagicMock()
            mock_pool.enqueue_job = AsyncMock()
            mock_pool.set = AsyncMock()
            mock_pool.get = AsyncMock(return_value=None)
            app.state.arq_pool = mock_pool

    async def test_generate_with_optional_steering_prompt(self, client, user_auth_headers):
        """steering_prompt is optional — omitting it should still return 202."""
        resp = await client.post(
            "/scenarios/generate",
            json=make_scenario_generate_payload(
                target_system_prompt="You are a bot.",
                user_objective="Test",
                count=1,
            ),
            headers=user_auth_headers,
        )
        assert resp.status_code == 202
        assert "job_id" in resp.json()

    async def test_get_job_partial_status(self, client, user_auth_headers):
        job_state = {
            "job_id": "partial-job-456",
            "status": "partial",
            "count_requested": 3,
            "count_succeeded": 2,
            "scenarios": [
                {
                    "yaml": "version: '1.0'\nid: s1",
                    "name": "Scenario 1",
                    "type": "adversarial",
                    "technique": "role_play",
                    "turns": 2,
                },
                {
                    "yaml": "version: '1.0'\nid: s2",
                    "name": "Scenario 2",
                    "type": "adversarial",
                    "technique": "dan_prompt",
                    "turns": 2,
                },
            ],
            "errors": ["Scenario 3: Validation failed: bot: Field required"],
            "created_at": "2026-03-02T00:00:00+00:00",
            "completed_at": "2026-03-02T00:00:30+00:00",
        }
        app.state.arq_pool.get.return_value = json.dumps(job_state).encode()

        resp = await client.get(
            "/scenarios/generate/partial-job-456",
            headers=user_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "partial"
        assert data["count_succeeded"] == 2
        assert len(data["scenarios"]) == 2
        assert len(data["errors"]) == 1

        app.state.arq_pool.get.return_value = None
