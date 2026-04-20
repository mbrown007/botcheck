from __future__ import annotations

from botcheck_api import metrics as api_metrics
from runs_test_helpers import _other_tenant_headers

from factories import make_grai_eval_suite_payload, make_promptfoo_yaml


async def test_grai_suite_direct_crud_lifecycle(client, user_auth_headers):
    create_resp = await client.post(
        "/grai/suites",
        json=make_grai_eval_suite_payload(),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    suite_id = created["suite_id"]
    assert created["name"] == "Billing Eval Suite"
    assert created["source_yaml"] is None
    assert created["prompts"][0]["label"] == "helpful"
    assert created["cases"][0]["assert_json"][0]["assertion_type"] == "contains"

    list_resp = await client.get("/grai/suites", headers=user_auth_headers)
    assert list_resp.status_code == 200
    assert list_resp.json()[0]["suite_id"] == suite_id
    assert list_resp.json()[0]["prompt_count"] == 1
    assert list_resp.json()[0]["case_count"] == 1

    get_resp = await client.get(f"/grai/suites/{suite_id}", headers=user_auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["suite_id"] == suite_id

    update_resp = await client.put(
        f"/grai/suites/{suite_id}",
        json=make_grai_eval_suite_payload(name="Billing Eval Suite Updated"),
        headers=user_auth_headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Billing Eval Suite Updated"

    delete_resp = await client.delete(f"/grai/suites/{suite_id}", headers=user_auth_headers)
    assert delete_resp.status_code == 204

    missing_resp = await client.get(f"/grai/suites/{suite_id}", headers=user_auth_headers)
    assert missing_resp.status_code == 404
    assert missing_resp.json()["error_code"] == "grai_eval_suite_not_found"


async def test_grai_suite_import_persists_source_yaml_and_compiled_rows(client, user_auth_headers):
    yaml_content = make_promptfoo_yaml()

    resp = await client.post(
        "/grai/suites/import",
        json={"yaml_content": yaml_content},
        headers=user_auth_headers,
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["source_yaml"] == yaml_content
    assert body["name"] == "Billing support eval"
    assert body["prompts"][0]["label"] == "helpful"
    assert body["cases"][0]["assert_json"][0]["assertion_type"] == "contains"


async def test_grai_suite_import_returns_full_pass_diagnostics(client, user_auth_headers):
    yaml_content = make_promptfoo_yaml(
        overrides={
            "providers": ["openai:gpt-4.1"],
            "tests": [
                {
                    "description": "Unsupported",
                    "hooks": {"beforeAll": "node hook.js"},
                    "vars": {"question": "Hi"},
                    "assert": [{"type": "javascript", "value": "return true"}],
                }
            ],
        }
    )

    resp = await client.post(
        "/grai/suites/import",
        json={"yaml_content": yaml_content},
        headers=user_auth_headers,
    )

    assert resp.status_code == 422
    body = resp.json()
    assert body["error_code"] == "grai_import_invalid"
    assert len(body["diagnostics"]) >= 3
    assert any(item["feature_name"] == "providers" for item in body["diagnostics"])
    assert any(item["feature_name"] == "hooks" for item in body["diagnostics"])
    assert any(item["feature_name"] == "javascript" for item in body["diagnostics"])


async def test_grai_suite_import_updates_observability_metrics(client, user_auth_headers):
    success_before = api_metrics.GRAI_EVAL_IMPORT_TOTAL.labels(outcome="success")._value.get()
    compile_error_before = api_metrics.GRAI_EVAL_IMPORT_TOTAL.labels(outcome="compile_error")._value.get()

    success_resp = await client.post(
        "/grai/suites/import",
        json={"yaml_content": make_promptfoo_yaml()},
        headers=user_auth_headers,
    )
    assert success_resp.status_code == 201

    invalid_resp = await client.post(
        "/grai/suites/import",
        json={
            "yaml_content": make_promptfoo_yaml(
                overrides={
                    "providers": ["openai:gpt-4.1"],
                    "tests": [
                        {
                            "description": "Unsupported",
                            "hooks": {"beforeAll": "node hook.js"},
                            "vars": {"question": "Hi"},
                            "assert": [{"type": "javascript", "value": "return true"}],
                        }
                    ],
                }
            )
        },
        headers=user_auth_headers,
    )
    assert invalid_resp.status_code == 422

    assert api_metrics.GRAI_EVAL_IMPORT_TOTAL.labels(outcome="success")._value.get() == success_before + 1
    assert (
        api_metrics.GRAI_EVAL_IMPORT_TOTAL.labels(outcome="compile_error")._value.get()
        == compile_error_before + 1
    )


async def test_grai_suite_cross_tenant_read_and_mutation_return_404(client, user_auth_headers):
    create_resp = await client.post(
        "/grai/suites",
        json=make_grai_eval_suite_payload(),
        headers=user_auth_headers,
    )
    assert create_resp.status_code == 201
    suite_id = create_resp.json()["suite_id"]
    other_headers = _other_tenant_headers()

    get_resp = await client.get(f"/grai/suites/{suite_id}", headers=other_headers)
    # 403 from require_tenant_match OR 404 from get_grai_eval_suite_for_tenant; either is acceptable.
    assert get_resp.status_code in (403, 404)

    update_resp = await client.put(
        f"/grai/suites/{suite_id}",
        json=make_grai_eval_suite_payload(name="Other Tenant Update"),
        headers=other_headers,
    )
    assert update_resp.status_code in (403, 404)

    delete_resp = await client.delete(f"/grai/suites/{suite_id}", headers=other_headers)
    assert delete_resp.status_code in (403, 404)
