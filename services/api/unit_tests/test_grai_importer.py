from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from botcheck_api.grai.importer import SUPPORTED_ASSERTION_TYPES, compile_promptfoo_yaml
from botcheck_api.grai.schemas import GraiEvalSuiteUpsertRequest
from botcheck_api.grai.service_models import GraiImportValidationError
from botcheck_api.main import app


def _make_promptfoo_yaml(
    *,
    description: str = "Billing support eval",
    assertion_type: str = "contains",
    assertion_value: object = "refund",
    overrides: dict[str, object] | None = None,
) -> str:
    payload: dict[str, object] = {
        "description": description,
        "prompts": [
            {
                "label": "helpful",
                "raw": "Answer the user question clearly: {{question}}",
            }
        ],
        "tests": [
            {
                "description": "Refund policy",
                "vars": {"question": "What is the refund policy?"},
                "tags": ["billing", "smoke-test"],
                "threshold": 0.8,
                "assert": [
                    {
                        "type": assertion_type,
                        "value": assertion_value,
                        "weight": 1.0,
                    }
                ],
            }
        ],
    }
    if overrides:
        payload.update(overrides)
    return yaml.safe_dump(payload, sort_keys=False)


@pytest.mark.parametrize("assertion_type", SUPPORTED_ASSERTION_TYPES)
def test_compile_promptfoo_yaml_accepts_allowlisted_assertion_types(assertion_type: str) -> None:
    compiled = compile_promptfoo_yaml(
        yaml_content=_make_promptfoo_yaml(assertion_type=assertion_type),
    )

    assert compiled.name == "Billing support eval"
    assert len(compiled.prompts) == 1
    assert len(compiled.cases) == 1
    assert compiled.cases[0].assert_json[0]["assertion_type"] == assertion_type


def test_compile_promptfoo_yaml_collects_multiple_diagnostics() -> None:
    with pytest.raises(GraiImportValidationError) as exc_info:
        compile_promptfoo_yaml(
            yaml_content=_make_promptfoo_yaml(
                overrides={
                    "providers": ["openai:gpt-4.1"],
                    "prompts": [{"file": "prompts/billing.txt"}],
                    "tests": [
                        {
                            "description": "Broken test",
                            "hooks": {"beforeAll": "node hook.js"},
                            "vars": {"question": "Hi"},
                            "assert": [{"type": "javascript", "value": "return true"}],
                        }
                    ],
                }
            )
        )

    diagnostics = exc_info.value.diagnostics
    assert len(diagnostics) >= 4
    assert any(item.feature_name == "providers" for item in diagnostics)
    assert any(item.feature_name == "file" for item in diagnostics)
    assert any(item.feature_name == "hooks" and item.case_index == 0 for item in diagnostics)
    assert any(item.feature_name == "javascript" and item.case_index == 0 for item in diagnostics)


def test_compile_promptfoo_yaml_uses_name_override_and_generated_prompt_label() -> None:
    compiled = compile_promptfoo_yaml(
        yaml_content=_make_promptfoo_yaml(
            overrides={
                "prompts": ["Answer the user question clearly: {{question}}"],
            }
        ),
        name_override="Imported Billing Suite",
    )

    assert compiled.name == "Imported Billing Suite"
    assert compiled.prompts[0].label == "Prompt 1"


def test_compile_promptfoo_yaml_preserves_case_metadata_for_http_request_context() -> None:
    compiled = compile_promptfoo_yaml(
        yaml_content=_make_promptfoo_yaml(
            overrides={
                "tests": [
                    {
                        "description": "Incident triage",
                        "vars": {"question": "What should I check first?"},
                        "metadata": {
                            "http_request_context": {
                                "dashboard_context": {
                                    "uid": "checkout-incident",
                                    "time_range": {"from": "now-15m", "to": "now"},
                                }
                            }
                        },
                        "assert": [{"type": "contains", "value": "check"}],
                    }
                ]
            }
        ),
    )

    assert compiled.cases[0].metadata_json["http_request_context"]["dashboard_context"]["uid"] == "checkout-incident"


def test_compile_promptfoo_yaml_rejects_duplicate_prompt_labels() -> None:
    with pytest.raises(GraiImportValidationError) as exc_info:
        compile_promptfoo_yaml(
            yaml_content=_make_promptfoo_yaml(
                overrides={
                    "prompts": [
                        {"label": "shared", "raw": "Prompt A"},
                        {"label": "shared", "raw": "Prompt B"},
                    ]
                }
            ),
        )

    assert any(item.feature_name == "shared" for item in exc_info.value.diagnostics)
    assert any("duplicate prompt label" in item.message for item in exc_info.value.diagnostics)


def test_grai_eval_suite_upsert_request_rejects_duplicate_prompt_labels() -> None:
    with pytest.raises(ValidationError, match="prompt labels must be unique within a suite"):
        GraiEvalSuiteUpsertRequest.model_validate(
            {
                "name": "Billing Eval Suite",
                "prompts": [
                    {"label": "shared", "prompt_text": "Prompt A"},
                    {"label": "shared", "prompt_text": "Prompt B"},
                ],
                "cases": [
                    {
                        "description": "Refund policy",
                        "vars_json": {"question": "What is the refund policy?"},
                        "assert_json": [
                            {
                                "assertion_type": "contains",
                                "raw_value": "refund",
                            }
                        ],
                    }
                ],
            }
        )


def test_grai_import_route_declares_422_diagnostics_schema() -> None:
    schema = app.openapi()
    responses = schema["paths"]["/grai/suites/import"]["post"]["responses"]

    assert "422" in responses
    assert responses["422"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/GraiImportErrorResponse"
    )
