from __future__ import annotations

import json
from typing import Any

import yaml

from ..models import GraiAssertionType
from .service_models import (
    GraiCompiledCase,
    GraiCompiledPrompt,
    GraiCompiledSuite,
    GraiImportDiagnostic,
    GraiImportValidationError,
)

SUPPORTED_ASSERTION_TYPES = tuple(member.value for member in GraiAssertionType)
_ALLOWED_TOP_LEVEL_FIELDS = {"description", "prompts", "tests", "tags", "metadata"}
_ALLOWED_PROMPT_FIELDS = {"label", "raw", "prompt", "text", "metadata"}
_ALLOWED_TEST_FIELDS = {"description", "vars", "assert", "tags", "threshold", "metadata", "notes"}
_ALLOWED_ASSERTION_FIELDS = {"type", "value", "threshold", "weight"}


def _normalize_text(value: object) -> str | None:
    candidate = str(value or "").strip()
    return candidate or None


def _normalize_metadata(value: object, diagnostics: list[GraiImportDiagnostic], path: str) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    diagnostics.append(
        GraiImportDiagnostic(
            message="metadata must be an object",
            path=path,
            feature_name="metadata",
        )
    )
    return {}


def _normalize_tags(value: object, diagnostics: list[GraiImportDiagnostic], path: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        diagnostics.append(
            GraiImportDiagnostic(
                message="tags must be a list of strings",
                path=path,
                feature_name="tags",
            )
        )
        return []
    normalized: list[str] = []
    for index, item in enumerate(value):
        text = _normalize_text(item)
        if text is None:
            diagnostics.append(
                GraiImportDiagnostic(
                    message="tag must be a non-empty string",
                    path=f"{path}[{index}]",
                    feature_name="tags",
                )
            )
            continue
        normalized.append(text)
    return normalized


def _normalize_raw_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        candidate = value.strip()
        return candidate or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    return json.dumps(value, sort_keys=True)


def _compile_assertion(
    raw_assertion: object,
    *,
    diagnostics: list[GraiImportDiagnostic],
    path: str,
    case_index: int,
) -> dict[str, Any] | None:
    if not isinstance(raw_assertion, dict):
        diagnostics.append(
            GraiImportDiagnostic(
                message="assertion must be an object",
                path=path,
                case_index=case_index,
            )
        )
        return None

    for key in sorted(set(raw_assertion) - _ALLOWED_ASSERTION_FIELDS):
        diagnostics.append(
            GraiImportDiagnostic(
                message=f"unsupported assertion field: {key}",
                path=f"{path}.{key}",
                feature_name=str(key),
                case_index=case_index,
            )
        )

    assertion_type = _normalize_text(raw_assertion.get("type"))
    if assertion_type is None:
        diagnostics.append(
            GraiImportDiagnostic(
                message="assertion type is required",
                path=f"{path}.type",
                feature_name="type",
                case_index=case_index,
            )
        )
        return None
    if assertion_type not in SUPPORTED_ASSERTION_TYPES:
        diagnostics.append(
            GraiImportDiagnostic(
                message=f"unsupported assertion type: {assertion_type}",
                path=f"{path}.type",
                feature_name=assertion_type,
                case_index=case_index,
            )
        )
        return None

    threshold = raw_assertion.get("threshold")
    if threshold is not None:
        try:
            threshold = float(threshold)
        except (TypeError, ValueError):
            diagnostics.append(
                GraiImportDiagnostic(
                    message="assertion threshold must be numeric",
                    path=f"{path}.threshold",
                    feature_name="threshold",
                    case_index=case_index,
                )
            )
            threshold = None

    weight = raw_assertion.get("weight", 1.0)
    try:
        weight = float(weight)
    except (TypeError, ValueError):
        diagnostics.append(
            GraiImportDiagnostic(
                message="assertion weight must be numeric",
                path=f"{path}.weight",
                feature_name="weight",
                case_index=case_index,
            )
        )
        weight = 1.0

    return {
        "assertion_type": assertion_type,
        "passed": None,
        "score": None,
        "threshold": threshold,
        "weight": weight,
        "raw_value": _normalize_raw_value(raw_assertion.get("value")),
        "failure_reason": None,
        "latency_ms": None,
    }


def compile_promptfoo_yaml(*, yaml_content: str, name_override: str | None = None) -> GraiCompiledSuite:
    diagnostics: list[GraiImportDiagnostic] = []
    try:
        loaded = yaml.safe_load(yaml_content)
    except yaml.YAMLError as exc:
        diagnostics.append(GraiImportDiagnostic(message=f"invalid YAML: {exc}", path="yaml"))
        raise GraiImportValidationError(diagnostics) from exc

    if not isinstance(loaded, dict):
        raise GraiImportValidationError(
            [GraiImportDiagnostic(message="promptfoo import must be a YAML object", path="yaml")]
        )

    for key in sorted(set(loaded) - _ALLOWED_TOP_LEVEL_FIELDS):
        diagnostics.append(
            GraiImportDiagnostic(
                message=f"unsupported top-level feature: {key}",
                path=key,
                feature_name=str(key),
            )
        )

    prompts_raw = loaded.get("prompts")
    prompts: list[GraiCompiledPrompt] = []
    if not isinstance(prompts_raw, list) or not prompts_raw:
        diagnostics.append(
            GraiImportDiagnostic(
                message="prompts must be a non-empty list",
                path="prompts",
                feature_name="prompts",
            )
        )
    else:
        seen_prompt_labels: set[str] = set()
        for index, raw_prompt in enumerate(prompts_raw):
            path = f"prompts[{index}]"
            if isinstance(raw_prompt, str):
                prompt_text = _normalize_text(raw_prompt)
                if prompt_text is None:
                    diagnostics.append(
                        GraiImportDiagnostic(
                            message="prompt text must be a non-empty string",
                            path=path,
                        )
                    )
                    continue
                label = f"Prompt {index + 1}"
                if label in seen_prompt_labels:
                    diagnostics.append(
                        GraiImportDiagnostic(
                            message=f"duplicate prompt label: {label}",
                            path=path,
                            feature_name=label,
                        )
                    )
                    continue
                seen_prompt_labels.add(label)
                prompts.append(
                    GraiCompiledPrompt(
                        label=label,
                        prompt_text=prompt_text,
                    )
                )
                continue
            if not isinstance(raw_prompt, dict):
                diagnostics.append(
                    GraiImportDiagnostic(
                        message="prompt entry must be a string or object",
                        path=path,
                    )
                )
                continue
            for key in sorted(set(raw_prompt) - _ALLOWED_PROMPT_FIELDS):
                diagnostics.append(
                    GraiImportDiagnostic(
                        message=f"unsupported prompt feature: {key}",
                        path=f"{path}.{key}",
                        feature_name=str(key),
                    )
                )
            prompt_text = _normalize_text(
                raw_prompt.get("raw") or raw_prompt.get("prompt") or raw_prompt.get("text")
            )
            if prompt_text is None:
                diagnostics.append(
                    GraiImportDiagnostic(
                        message="prompt text is required",
                        path=path,
                    )
                )
                continue
            label = _normalize_text(raw_prompt.get("label")) or f"Prompt {index + 1}"
            if label in seen_prompt_labels:
                diagnostics.append(
                    GraiImportDiagnostic(
                        message=f"duplicate prompt label: {label}",
                        path=f"{path}.label",
                        feature_name=label,
                    )
                )
                continue
            seen_prompt_labels.add(label)
            prompts.append(
                GraiCompiledPrompt(
                    label=label,
                    prompt_text=prompt_text,
                    metadata_json=_normalize_metadata(
                        raw_prompt.get("metadata"),
                        diagnostics,
                        f"{path}.metadata",
                    ),
                )
            )

    tests_raw = loaded.get("tests")
    cases: list[GraiCompiledCase] = []
    if not isinstance(tests_raw, list) or not tests_raw:
        diagnostics.append(
            GraiImportDiagnostic(
                message="tests must be a non-empty list",
                path="tests",
                feature_name="tests",
            )
        )
    else:
        for index, raw_case in enumerate(tests_raw):
            path = f"tests[{index}]"
            if not isinstance(raw_case, dict):
                diagnostics.append(
                    GraiImportDiagnostic(
                        message="test entry must be an object",
                        path=path,
                        case_index=index,
                    )
                )
                continue
            for key in sorted(set(raw_case) - _ALLOWED_TEST_FIELDS):
                diagnostics.append(
                    GraiImportDiagnostic(
                        message=f"unsupported test feature: {key}",
                        path=f"{path}.{key}",
                        feature_name=str(key),
                        case_index=index,
                    )
                )
            vars_json = raw_case.get("vars") or {}
            if not isinstance(vars_json, dict):
                diagnostics.append(
                    GraiImportDiagnostic(
                        message="vars must be an object",
                        path=f"{path}.vars",
                        feature_name="vars",
                        case_index=index,
                    )
                )
                vars_json = {}

            raw_assertions = raw_case.get("assert")
            compiled_assertions: list[dict[str, Any]] = []
            if not isinstance(raw_assertions, list) or not raw_assertions:
                diagnostics.append(
                    GraiImportDiagnostic(
                        message="assert must be a non-empty list",
                        path=f"{path}.assert",
                        feature_name="assert",
                        case_index=index,
                    )
                )
            else:
                for assertion_index, raw_assertion in enumerate(raw_assertions):
                    compiled = _compile_assertion(
                        raw_assertion,
                        diagnostics=diagnostics,
                        path=f"{path}.assert[{assertion_index}]",
                        case_index=index,
                    )
                    if compiled is not None:
                        compiled_assertions.append(compiled)

            if not compiled_assertions:
                # All assertions for this case failed compilation; diagnostics already
                # contain at least one entry — skip the case to avoid storing an
                # empty-assertion row that would pass validation silently.
                continue

            import_threshold = raw_case.get("threshold")
            if import_threshold is not None:
                try:
                    import_threshold = float(import_threshold)
                except (TypeError, ValueError):
                    diagnostics.append(
                        GraiImportDiagnostic(
                            message="threshold must be numeric",
                            path=f"{path}.threshold",
                            feature_name="threshold",
                            case_index=index,
                        )
                    )
                    import_threshold = None

            cases.append(
                GraiCompiledCase(
                    description=_normalize_text(raw_case.get("description")),
                    vars_json=dict(vars_json),
                    assert_json=compiled_assertions,
                    tags_json=_normalize_tags(raw_case.get("tags"), diagnostics, f"{path}.tags"),
                    metadata_json=_normalize_metadata(raw_case.get("metadata"), diagnostics, f"{path}.metadata"),
                    import_threshold=import_threshold,
                )
            )

    metadata_json = _normalize_metadata(loaded.get("metadata"), diagnostics, "metadata")

    if diagnostics:
        raise GraiImportValidationError(diagnostics)

    name = _normalize_text(name_override) or _normalize_text(loaded.get("description")) or "Imported Eval Suite"
    return GraiCompiledSuite(
        name=name,
        description=_normalize_text(loaded.get("description")),
        prompts=prompts,
        cases=cases,
        metadata_json=metadata_json,
        source_yaml=yaml_content,
    )
