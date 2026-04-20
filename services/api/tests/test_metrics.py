from unittest.mock import AsyncMock, MagicMock, patch

from factories import make_run_create_payload


def _livekit_mock():
    m = MagicMock()
    m.room.create_room = AsyncMock(return_value=MagicMock())
    m.agent_dispatch.create_dispatch = AsyncMock(return_value=MagicMock())
    m.sip.create_sip_participant = AsyncMock(return_value=MagicMock())
    m.aclose = AsyncMock()
    return m


def _metrics_auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer botcheck-dev-metrics-token"}


async def test_metrics_endpoint_requires_bearer_scrape_token(client, monkeypatch):
    monkeypatch.setattr("botcheck_api.shared.health_router.settings.metrics_scrape_token", "metrics-secret")

    missing_resp = await client.get("/metrics")
    assert missing_resp.status_code == 401
    assert missing_resp.headers["WWW-Authenticate"] == "Bearer"

    wrong_resp = await client.get(
        "/metrics",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert wrong_resp.status_code == 401
    assert wrong_resp.headers["WWW-Authenticate"] == "Bearer"

    # Wrong scheme (not Bearer) must also be rejected even with the correct token value
    wrong_scheme_resp = await client.get(
        "/metrics",
        headers={"Authorization": "Token metrics-secret"},
    )
    assert wrong_scheme_resp.status_code == 401
    assert wrong_scheme_resp.headers["WWW-Authenticate"] == "Bearer"

    # Bare Bearer header with no token value must be rejected
    bare_bearer_resp = await client.get(
        "/metrics",
        headers={"Authorization": "Bearer "},
    )
    assert bare_bearer_resp.status_code == 401
    assert bare_bearer_resp.headers["WWW-Authenticate"] == "Bearer"


@patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
async def test_metrics_endpoint_exposes_botcheck_counters(
    mock_lk_class,
    client,
    uploaded_scenario,
    user_auth_headers,
    monkeypatch,
):
    mock_lk_class.return_value = _livekit_mock()
    monkeypatch.setattr("botcheck_api.shared.health_router.settings.metrics_scrape_token", "botcheck-dev-metrics-token")

    create_resp = await client.post(
        "/runs/",
        json=make_run_create_payload(uploaded_scenario["id"]),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 202

    metrics_resp = await client.get("/metrics", headers=_metrics_auth_headers())
    assert metrics_resp.status_code == 200
    assert "botcheck_api_http_requests_total" in metrics_resp.text
    assert "botcheck_runs_created_total" in metrics_resp.text
    assert "botcheck_run_state_transitions_total" in metrics_resp.text
    assert 'path="/metrics"' not in metrics_resp.text
