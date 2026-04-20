from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from jose import jwt

from botcheck_api.config import settings
from botcheck_api.main import app
from botcheck_api.scenarios.schemas import GenerateJobStatus

from factories import (
    make_grai_eval_run_payload,
    make_grai_eval_suite_payload,
    make_http_destination_payload,
    make_pack_upsert_payload,
    make_playground_run_payload,
    make_promptfoo_yaml,
    make_run_create_payload,
    make_schedule_create_payload,
    make_scenario_upload_payload,
    make_scenario_yaml,
)
from runs_test_helpers import _livekit_mock


def _role_auth_headers(role: str, *, tenant_id: str | None = None) -> dict[str, str]:
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


def _persona_payload() -> dict[str, object]:
    return {
        "name": "Role Persona",
        "system_prompt": "Act as a realistic customer caller.",
        "style": "neutral",
        "voice": "alloy",
        "is_active": True,
    }


def _sip_payload() -> dict[str, object]:
    return {
        "name": "Role Destination",
        "protocol": "sip",
        "endpoint": "sip:bot@carrier.example.com",
        "caller_id": "+15551230000",
        "trunk_id": "trunk-a",
        "headers": {"X-Region": "us-east-1"},
        "is_active": True,
        "provisioned_channels": 10,
        "reserved_channels": 2,
        "capacity_scope": "carrier-a",
    }


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 403), ("operator", 202), ("admin", 202), ("system_admin", 202)],
)
@patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
async def test_create_run_enforces_operator_minimum(
    mock_lk_class,
    role,
    expected_status,
    client,
    uploaded_scenario,
):
    mock_lk_class.return_value = _livekit_mock()

    resp = await client.post(
        "/runs/",
        json=make_run_create_payload(uploaded_scenario["id"]),
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 403), ("operator", 403), ("editor", 202), ("system_admin", 202)],
)
@patch("botcheck_api.runs.service_lifecycle.lk_api.LiveKitAPI")
async def test_create_playground_run_enforces_editor_minimum(
    mock_lk_class,
    role,
    expected_status,
    client,
    uploaded_scenario,
):
    mock_lk_class.return_value = _livekit_mock()

    resp = await client.post(
        "/runs/playground",
        json=make_playground_run_payload(
            scenario_id=uploaded_scenario["id"],
            playground_mode="mock",
            system_prompt="You are a playground mock.",
        ),
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 200), ("operator", 200), ("editor", 200), ("system_admin", 200)],
)
async def test_list_playground_presets_enforces_viewer_minimum(
    role,
    expected_status,
    client,
):
    resp = await client.get(
        "/runs/playground/presets",
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 403), ("operator", 201), ("editor", 201), ("system_admin", 201)],
)
async def test_create_playground_preset_enforces_operator_minimum(
    role,
    expected_status,
    client,
    uploaded_scenario,
):
    resp = await client.post(
        "/runs/playground/presets",
        json={
            "name": f"{role} preset",
            "scenario_id": uploaded_scenario["id"],
            "playground_mode": "mock",
            "system_prompt": "You are a test bot.",
        },
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 403), ("operator", 200), ("editor", 200), ("system_admin", 200)],
)
async def test_update_playground_preset_enforces_operator_minimum(
    role,
    expected_status,
    client,
    uploaded_scenario,
):
    create_resp = await client.post(
        "/runs/playground/presets",
        json={
            "name": "role-preset-update",
            "scenario_id": uploaded_scenario["id"],
            "playground_mode": "mock",
            "system_prompt": "You are a test bot.",
        },
        headers=_role_auth_headers("operator"),
    )
    assert create_resp.status_code == 201
    preset_id = create_resp.json()["preset_id"]

    resp = await client.patch(
        f"/runs/playground/presets/{preset_id}",
        json={"name": f"{role} renamed preset"},
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 403), ("operator", 204), ("editor", 204), ("system_admin", 204)],
)
async def test_delete_playground_preset_enforces_operator_minimum(
    role,
    expected_status,
    client,
    uploaded_scenario,
):
    create_resp = await client.post(
        "/runs/playground/presets",
        json={
            "name": "role-preset-delete",
            "scenario_id": uploaded_scenario["id"],
            "playground_mode": "mock",
            "system_prompt": "You are a test bot.",
        },
        headers=_role_auth_headers("operator"),
    )
    assert create_resp.status_code == 201
    preset_id = create_resp.json()["preset_id"]

    resp = await client.delete(
        f"/runs/playground/presets/{preset_id}",
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 200), ("operator", 200), ("editor", 200), ("admin", 200), ("system_admin", 200)],
)
async def test_list_grai_suites_enforces_viewer_minimum(
    role,
    expected_status,
    client,
):
    resp = await client.get("/grai/suites", headers=_role_auth_headers(role))

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 403), ("operator", 403), ("editor", 201), ("admin", 201), ("system_admin", 201)],
)
async def test_create_grai_suite_enforces_editor_minimum(
    role,
    expected_status,
    client,
):
    resp = await client.post(
        "/grai/suites",
        json=make_grai_eval_suite_payload(name=f"{role} suite"),
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 403), ("operator", 403), ("editor", 201), ("admin", 201), ("system_admin", 201)],
)
async def test_import_grai_suite_enforces_editor_minimum(
    role,
    expected_status,
    client,
):
    resp = await client.post(
        "/grai/suites/import",
        json={"yaml_content": make_promptfoo_yaml(), "name": f"{role} imported suite"},
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 403), ("operator", 403), ("editor", 200), ("admin", 200), ("system_admin", 200)],
)
async def test_update_grai_suite_enforces_editor_minimum(
    role,
    expected_status,
    client,
):
    create_resp = await client.post(
        "/grai/suites",
        json=make_grai_eval_suite_payload(name="role-grai-update"),
        headers=_role_auth_headers("editor"),
    )
    assert create_resp.status_code == 201
    suite_id = create_resp.json()["suite_id"]

    resp = await client.put(
        f"/grai/suites/{suite_id}",
        json=make_grai_eval_suite_payload(name=f"{role} updated suite"),
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 403), ("operator", 403), ("editor", 204), ("admin", 204), ("system_admin", 204)],
)
async def test_delete_grai_suite_enforces_editor_minimum(
    role,
    expected_status,
    client,
):
    create_resp = await client.post(
        "/grai/suites",
        json=make_grai_eval_suite_payload(name="role-grai-delete"),
        headers=_role_auth_headers("editor"),
    )
    assert create_resp.status_code == 201
    suite_id = create_resp.json()["suite_id"]

    resp = await client.delete(
        f"/grai/suites/{suite_id}",
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 403), ("operator", 202), ("editor", 202), ("admin", 202), ("system_admin", 202)],
)
async def test_create_grai_run_enforces_operator_minimum(
    role,
    expected_status,
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)
    suite_resp = await client.post(
        "/grai/suites",
        json=make_grai_eval_suite_payload(name=f"role-grai-run-suite-{role}"),
        headers=_role_auth_headers("editor"),
    )
    assert suite_resp.status_code == 201
    suite_id = suite_resp.json()["suite_id"]
    destination_resp = await client.post(
        "/destinations/",
        json=make_http_destination_payload(name=f"role-grai-run-dest-{role}"),
        headers=_role_auth_headers("editor"),
    )
    assert destination_resp.status_code == 201
    transport_profile_id = destination_resp.json()["transport_profile_id"]

    resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_profile_id,
        ),
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 200), ("operator", 200), ("editor", 200), ("admin", 200), ("system_admin", 200)],
)
async def test_list_grai_suite_runs_enforces_viewer_minimum(
    role,
    expected_status,
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)
    suite_resp = await client.post(
        "/grai/suites",
        json=make_grai_eval_suite_payload(name=f"role-grai-run-history-suite-{role}"),
        headers=_role_auth_headers("editor"),
    )
    assert suite_resp.status_code == 201
    suite_id = suite_resp.json()["suite_id"]

    resp = await client.get(
        f"/grai/suites/{suite_id}/runs",
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


async def test_list_grai_suite_runs_rejects_unauthenticated(client, monkeypatch):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)
    suite_resp = await client.post(
        "/grai/suites",
        json=make_grai_eval_suite_payload(name="role-grai-run-history-unauth"),
        headers=_role_auth_headers("editor"),
    )
    assert suite_resp.status_code == 201
    suite_id = suite_resp.json()["suite_id"]

    resp = await client.get(f"/grai/suites/{suite_id}/runs")

    assert resp.status_code == 401


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 200), ("operator", 200), ("editor", 200), ("admin", 200), ("system_admin", 200)],
)
async def test_get_grai_run_enforces_viewer_minimum(
    role,
    expected_status,
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)
    suite_resp = await client.post(
        "/grai/suites",
        json=make_grai_eval_suite_payload(name=f"role-grai-run-read-suite-{role}"),
        headers=_role_auth_headers("editor"),
    )
    assert suite_resp.status_code == 201
    suite_id = suite_resp.json()["suite_id"]
    destination_resp = await client.post(
        "/destinations/",
        json=make_http_destination_payload(name=f"role-grai-run-read-dest-{role}"),
        headers=_role_auth_headers("editor"),
    )
    assert destination_resp.status_code == 201
    transport_profile_id = destination_resp.json()["transport_profile_id"]
    run_resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_profile_id,
        ),
        headers=_role_auth_headers("operator"),
    )
    assert run_resp.status_code == 202
    eval_run_id = run_resp.json()["eval_run_id"]

    resp = await client.get(
        f"/grai/runs/{eval_run_id}",
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 200), ("operator", 200), ("editor", 200), ("admin", 200), ("system_admin", 200)],
)
async def test_get_grai_run_progress_enforces_viewer_minimum(
    role,
    expected_status,
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)
    suite_resp = await client.post(
        "/grai/suites",
        json=make_grai_eval_suite_payload(name=f"role-grai-run-progress-suite-{role}"),
        headers=_role_auth_headers("editor"),
    )
    assert suite_resp.status_code == 201
    suite_id = suite_resp.json()["suite_id"]
    destination_resp = await client.post(
        "/destinations/",
        json=make_http_destination_payload(name=f"role-grai-run-progress-dest-{role}"),
        headers=_role_auth_headers("editor"),
    )
    assert destination_resp.status_code == 201
    transport_profile_id = destination_resp.json()["transport_profile_id"]
    run_resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_profile_id,
        ),
        headers=_role_auth_headers("operator"),
    )
    assert run_resp.status_code == 202
    eval_run_id = run_resp.json()["eval_run_id"]

    resp = await client.get(
        f"/grai/runs/{eval_run_id}/progress",
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 200), ("operator", 200), ("editor", 200), ("admin", 200), ("system_admin", 200)],
)
async def test_get_grai_run_report_enforces_viewer_minimum(
    role,
    expected_status,
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)
    suite_resp = await client.post(
        "/grai/suites",
        json=make_grai_eval_suite_payload(name=f"role-grai-run-report-suite-{role}"),
        headers=_role_auth_headers("editor"),
    )
    assert suite_resp.status_code == 201
    suite_id = suite_resp.json()["suite_id"]
    destination_resp = await client.post(
        "/destinations/",
        json=make_http_destination_payload(name=f"role-grai-run-report-dest-{role}"),
        headers=_role_auth_headers("editor"),
    )
    assert destination_resp.status_code == 201
    transport_profile_id = destination_resp.json()["transport_profile_id"]
    run_resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_profile_id,
        ),
        headers=_role_auth_headers("operator"),
    )
    assert run_resp.status_code == 202
    eval_run_id = run_resp.json()["eval_run_id"]

    resp = await client.get(
        f"/grai/runs/{eval_run_id}/report",
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 200), ("operator", 200), ("editor", 200), ("admin", 200), ("system_admin", 200)],
)
async def test_list_grai_run_results_enforces_viewer_minimum(
    role,
    expected_status,
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)
    suite_resp = await client.post(
        "/grai/suites",
        json=make_grai_eval_suite_payload(name=f"role-grai-run-results-suite-{role}"),
        headers=_role_auth_headers("editor"),
    )
    assert suite_resp.status_code == 201
    suite_id = suite_resp.json()["suite_id"]
    destination_resp = await client.post(
        "/destinations/",
        json=make_http_destination_payload(name=f"role-grai-run-results-dest-{role}"),
        headers=_role_auth_headers("editor"),
    )
    assert destination_resp.status_code == 201
    transport_profile_id = destination_resp.json()["transport_profile_id"]
    run_resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_profile_id,
        ),
        headers=_role_auth_headers("operator"),
    )
    assert run_resp.status_code == 202
    eval_run_id = run_resp.json()["eval_run_id"]

    resp = await client.get(
        f"/grai/runs/{eval_run_id}/results",
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 403), ("operator", 200), ("editor", 200), ("admin", 200), ("system_admin", 200)],
)
async def test_cancel_grai_run_enforces_operator_minimum(
    role,
    expected_status,
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)
    suite_resp = await client.post(
        "/grai/suites",
        json=make_grai_eval_suite_payload(name=f"role-grai-run-cancel-suite-{role}"),
        headers=_role_auth_headers("editor"),
    )
    assert suite_resp.status_code == 201
    suite_id = suite_resp.json()["suite_id"]
    destination_resp = await client.post(
        "/destinations/",
        json=make_http_destination_payload(name=f"role-grai-run-cancel-dest-{role}"),
        headers=_role_auth_headers("editor"),
    )
    assert destination_resp.status_code == 201
    transport_profile_id = destination_resp.json()["transport_profile_id"]
    run_resp = await client.post(
        "/grai/runs",
        json=make_grai_eval_run_payload(
            suite_id=suite_id,
            transport_profile_id=transport_profile_id,
        ),
        headers=_role_auth_headers("operator"),
    )
    assert run_resp.status_code == 202
    eval_run_id = run_resp.json()["eval_run_id"]

    resp = await client.post(
        f"/grai/runs/{eval_run_id}/cancel",
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("path", "role", "expected_status"),
    [
        ("/tenants/me/providers/usage", "viewer", 403),
        ("/tenants/me/providers/usage", "operator", 200),
        ("/tenants/me/providers/usage", "editor", 200),
        ("/tenants/me/providers/usage", "admin", 200),
        ("/tenants/me/providers/usage", "system_admin", 200),
        ("/tenants/me/providers/quota", "viewer", 403),
        ("/tenants/me/providers/quota", "operator", 200),
        ("/tenants/me/providers/quota", "editor", 200),
        ("/tenants/me/providers/quota", "admin", 200),
        ("/tenants/me/providers/quota", "system_admin", 200),
    ],
)
async def test_tenant_provider_usage_routes_enforce_operator_minimum(
    path,
    role,
    expected_status,
    client,
):
    resp = await client.get(path, headers=_role_auth_headers(role))

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 403), ("operator", 403), ("editor", 200), ("system_admin", 200)],
)
async def test_playground_extract_tools_enforces_editor_minimum(
    role,
    expected_status,
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        "botcheck_api.runs.runs_lifecycle.extract_tool_signatures",
        AsyncMock(return_value=[]),
    )

    resp = await client.post(
        "/runs/playground/extract-tools",
        json={"system_prompt": "You can call lookup_account(account_id)."},
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 403), ("operator", 403), ("editor", 201), ("system_admin", 201)],
)
async def test_create_schedule_enforces_editor_minimum(
    role,
    expected_status,
    client,
    uploaded_scenario,
):
    resp = await client.post(
        "/schedules/",
        json=make_schedule_create_payload(uploaded_scenario["id"], cron_expr="*/15 * * * *"),
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 403), ("operator", 403), ("editor", 201), ("system_admin", 201)],
)
async def test_create_scenario_enforces_editor_minimum(role, expected_status, client):
    yaml_content = make_scenario_yaml(
        scenario_id=f"role-scenario-{role}",
        name=f"Role Scenario {role}",
    )

    resp = await client.post(
        "/scenarios/",
        json=make_scenario_upload_payload(yaml_content),
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 403), ("operator", 403), ("editor", 202), ("system_admin", 202)],
)
async def test_cache_rebuild_enforces_editor_minimum(
    role,
    expected_status,
    client,
    uploaded_scenario,
):
    resp = await client.post(
        f"/scenarios/{uploaded_scenario['id']}/cache/rebuild",
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 403), ("editor", 403), ("admin", 202), ("system_admin", 202)],
)
async def test_generate_start_enforces_admin_minimum(role, expected_status, client):
    resp = await client.post(
        "/scenarios/generate",
        json={
            "target_system_prompt": "You are a reservation bot.",
            "steering_prompt": "Generate adversarial tests.",
            "user_objective": "Recover an airline booking.",
            "count": 1,
        },
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 403), ("editor", 403), ("admin", 200), ("system_admin", 200)],
)
async def test_generate_status_enforces_admin_minimum(role, expected_status, client):
    app.state.arq_pool.get = AsyncMock(
        return_value=GenerateJobStatus(
            job_id="role-job-1",
            status="complete",
            count_requested=1,
            count_succeeded=1,
            scenarios=[],
            errors=[],
            created_at="2026-03-10T12:00:00Z",
            completed_at="2026-03-10T12:01:00Z",
        ).model_dump_json()
    )

    resp = await client.get(
        "/scenarios/generate/role-job-1",
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 403), ("editor", 403), ("admin", 201), ("system_admin", 201)],
)
async def test_create_ai_persona_enforces_admin_minimum(
    role,
    expected_status,
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_ai_scenarios_enabled", True)

    resp = await client.post(
        "/scenarios/personas",
        json=_persona_payload(),
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 403), ("operator", 403), ("editor", 201), ("system_admin", 201)],
)
async def test_create_destination_enforces_editor_minimum(
    role,
    expected_status,
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_destinations_enabled", True)

    resp = await client.post(
        "/destinations/",
        json=_sip_payload(),
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 403), ("editor", 403), ("admin", 201), ("system_admin", 201)],
)
async def test_create_pack_enforces_admin_minimum(
    role,
    expected_status,
    client,
    uploaded_scenario,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)

    resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Role Pack",
            scenario_ids=[uploaded_scenario["id"]],
        ),
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [("viewer", 403), ("editor", 403), ("admin", 202), ("system_admin", 202)],
)
async def test_run_pack_enforces_admin_minimum(
    role,
    expected_status,
    client,
    uploaded_scenario,
    monkeypatch,
):
    monkeypatch.setattr(settings, "feature_packs_enabled", True)

    create_resp = await client.post(
        "/packs/",
        json=make_pack_upsert_payload(
            name="Role Run Pack",
            scenario_ids=[uploaded_scenario["id"]],
        ),
        headers=_role_auth_headers("admin"),
    )
    assert create_resp.status_code == 201
    pack_id = create_resp.json()["pack_id"]

    resp = await client.post(
        f"/packs/{pack_id}/run",
        headers=_role_auth_headers(role),
    )

    assert resp.status_code == expected_status
