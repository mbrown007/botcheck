from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, NamedTuple

from pydantic import BaseModel, Field

GRAI_EVAL_DISPATCH_ERROR_PREFIX = "dispatch failed: "


@dataclass(slots=True)
class GraiImportDiagnostic:
    message: str
    path: str
    feature_name: str | None = None
    case_index: int | None = None


@dataclass(slots=True)
class GraiCompiledPrompt:
    label: str
    prompt_text: str
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GraiCompiledCase:
    description: str | None
    vars_json: dict[str, Any]
    assert_json: list[dict[str, Any]]
    tags_json: list[str]
    metadata_json: dict[str, Any]
    import_threshold: float | None = None


@dataclass(slots=True)
class GraiCompiledSuite:
    name: str
    description: str | None
    prompts: list[GraiCompiledPrompt]
    cases: list[GraiCompiledCase]
    metadata_json: dict[str, Any] = field(default_factory=dict)
    source_yaml: str | None = None


@dataclass(slots=True)
class GraiEvalRunDestinationSnapshot:
    destination_index: int
    transport_profile_id: str
    label: str
    protocol: str
    endpoint_at_start: str
    headers_at_start: dict[str, Any]
    direct_http_config_at_start: dict[str, Any] | None = None


class GraiEvalRunSnapshot(NamedTuple):
    eval_run_id: str
    tenant_id: str
    suite_id: str
    transport_profile_id: str
    transport_profile_ids: list[str]
    status: str
    terminal_outcome: str | None
    prompt_count: int
    case_count: int
    total_pairs: int
    endpoint_at_start: str
    headers_at_start: dict[str, Any]
    direct_http_config_at_start: dict[str, Any] | None
    destinations: list[GraiEvalRunDestinationSnapshot]
    trigger_source: str
    schedule_id: str | None
    triggered_by: str | None
    created_at: datetime
    updated_at: datetime


class GraiEvalRunCancelResult(NamedTuple):
    found: bool
    applied: bool
    status: str
    reason: str


class GraiEvalResultWritePayload(BaseModel):
    assertion_type: str
    passed: bool
    score: float | None = None
    threshold: float | None = None
    weight: float = 1.0
    raw_value: str | None = None
    failure_reason: str | None = None
    latency_ms: int | None = None
    tags_json: list[str] = Field(default_factory=list)
    raw_s3_key: str | None = None


class GraiImportValidationError(Exception):
    def __init__(self, diagnostics: list[GraiImportDiagnostic]) -> None:
        self.diagnostics = diagnostics
        super().__init__("Promptfoo import failed")
