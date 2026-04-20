from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..models import GraiAssertionType
from ..text_normalization import strip_nonempty, strip_or_none

SUPPORTED_ASSERTION_TYPES = tuple(member.value for member in GraiAssertionType)


class GraiEvalAssertionPayload(BaseModel):
    assertion_type: str = Field(min_length=1, max_length=64)
    raw_value: str | None = None
    threshold: float | None = None
    weight: float = Field(default=1.0, gt=0)

    @field_validator("assertion_type")
    @classmethod
    def _validate_assertion_type(cls, value: str) -> str:
        candidate = strip_nonempty(value)
        if candidate not in SUPPORTED_ASSERTION_TYPES:
            raise ValueError(f"unsupported assertion type: {candidate}")
        return candidate

    @field_validator("raw_value")
    @classmethod
    def _normalize_raw_value(cls, value: str | None) -> str | None:
        return strip_or_none(value)


class GraiEvalPromptPayload(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    prompt_text: str = Field(min_length=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("label", "prompt_text")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        return strip_nonempty(value)


class GraiEvalCasePayload(BaseModel):
    description: str | None = None
    vars_json: dict[str, Any] = Field(default_factory=dict)
    assert_json: list[GraiEvalAssertionPayload] = Field(default_factory=list)
    tags_json: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    import_threshold: float | None = None

    @field_validator("description")
    @classmethod
    def _normalize_description(cls, value: str | None) -> str | None:
        return strip_or_none(value)

    @field_validator("tags_json")
    @classmethod
    def _normalize_tags(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            candidate = item.strip()
            if not candidate:
                raise ValueError("tags must not contain blank strings")
            normalized.append(candidate)
        return normalized

    @model_validator(mode="after")
    def _require_assertions(self):
        if not self.assert_json:
            raise ValueError("assert_json must contain at least one assertion")
        return self


class GraiEvalSuiteUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    prompts: list[GraiEvalPromptPayload] = Field(default_factory=list)
    cases: list[GraiEvalCasePayload] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, value: object) -> object:
        if isinstance(value, str):
            return strip_nonempty(value, error_message="name must not be blank")
        return value

    @field_validator("description")
    @classmethod
    def _normalize_description(cls, value: str | None) -> str | None:
        return strip_or_none(value)

    @model_validator(mode="after")
    def _require_rows(self):
        if not self.prompts:
            raise ValueError("prompts must contain at least one prompt")
        if not self.cases:
            raise ValueError("cases must contain at least one case")
        labels = [prompt.label for prompt in self.prompts]
        if len(labels) != len(set(labels)):
            raise ValueError("prompt labels must be unique within a suite")
        return self


class GraiEvalSuiteImportRequest(BaseModel):
    yaml_content: str = Field(min_length=1)
    name: str | None = None

    @field_validator("yaml_content")
    @classmethod
    def _strip_yaml(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("yaml_content must not be blank")
        return value

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str | None) -> str | None:
        return strip_or_none(value)


class GraiEvalAssertionResponse(BaseModel):
    assertion_type: str
    passed: bool | None = None
    score: float | None = None
    threshold: float | None = None
    weight: float = 1.0
    raw_value: str | None = None
    failure_reason: str | None = None
    latency_ms: int | None = None


class GraiEvalPromptResponse(BaseModel):
    prompt_id: str
    label: str
    prompt_text: str
    metadata_json: dict[str, Any]


class GraiEvalCaseResponse(BaseModel):
    case_id: str
    description: str | None
    vars_json: dict[str, Any]
    assert_json: list[GraiEvalAssertionResponse]
    tags_json: list[str]
    metadata_json: dict[str, Any]
    import_threshold: float | None


class GraiEvalSuiteSummaryResponse(BaseModel):
    suite_id: str
    name: str
    description: str | None
    prompt_count: int
    case_count: int
    has_source_yaml: bool
    created_at: datetime
    updated_at: datetime


class GraiEvalSuiteDetailResponse(BaseModel):
    suite_id: str
    name: str
    description: str | None
    source_yaml: str | None
    metadata_json: dict[str, Any]
    prompts: list[GraiEvalPromptResponse]
    cases: list[GraiEvalCaseResponse]
    created_at: datetime
    updated_at: datetime


class GraiImportDiagnosticResponse(BaseModel):
    message: str
    path: str
    feature_name: str | None = None
    case_index: int | None = None


class GraiImportErrorResponse(BaseModel):
    error_code: str
    detail: str
    diagnostics: list[GraiImportDiagnosticResponse]


class GraiEvalRunCreateRequest(BaseModel):
    suite_id: str = Field(min_length=1, max_length=64)
    transport_profile_id: str | None = Field(default=None, min_length=1, max_length=64)
    transport_profile_ids: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("suite_id", "transport_profile_id")
    @classmethod
    def _normalize_required_ids(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return strip_nonempty(value)

    @field_validator("transport_profile_ids")
    @classmethod
    def _normalize_transport_profile_ids(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            candidate = item.strip()
            if not candidate:
                raise ValueError("transport_profile_ids must not contain blank values")
            if candidate in seen:
                raise ValueError("transport_profile_ids must not contain duplicates")
            normalized.append(candidate)
            seen.add(candidate)
        return normalized

    @model_validator(mode="after")
    def _require_transport_profiles(self):
        if self.transport_profile_id and self.transport_profile_ids:
            if self.transport_profile_ids[0] != self.transport_profile_id:
                raise ValueError(
                    "transport_profile_id must match the first item in transport_profile_ids"
                )
        if self.transport_profile_id and not self.transport_profile_ids:
            self.transport_profile_ids = [self.transport_profile_id]
        if not self.transport_profile_ids:
            raise ValueError("transport_profile_ids must contain at least one destination")
        return self


class GraiEvalRunDestinationResponse(BaseModel):
    destination_index: int
    transport_profile_id: str
    label: str
    protocol: str
    endpoint_at_start: str
    headers_at_start: dict[str, Any]
    direct_http_config_at_start: dict[str, Any] | None = None


class GraiEvalRunResponse(BaseModel):
    eval_run_id: str
    suite_id: str
    # Deprecated: always equals transport_profile_ids[0]. Kept for backward
    # compatibility with clients that pre-date multi-destination support.
    transport_profile_id: str
    transport_profile_ids: list[str]
    endpoint_at_start: str
    headers_at_start: dict[str, Any]
    direct_http_config_at_start: dict[str, Any] | None = None
    destinations: list[GraiEvalRunDestinationResponse]
    trigger_source: str
    schedule_id: str | None = None
    triggered_by: str | None = None
    status: str
    terminal_outcome: str | None = None
    prompt_count: int
    case_count: int
    total_pairs: int
    dispatched_count: int
    completed_count: int
    failed_count: int
    created_at: datetime
    updated_at: datetime


class GraiEvalRunHistoryDestinationResponse(BaseModel):
    destination_index: int
    transport_profile_id: str
    label: str


class GraiEvalRunHistoryResponse(BaseModel):
    eval_run_id: str
    suite_id: str
    transport_profile_id: str
    transport_profile_ids: list[str]
    destination_count: int
    destinations: list[GraiEvalRunHistoryDestinationResponse]
    status: str
    terminal_outcome: str | None = None
    trigger_source: str
    prompt_count: int
    case_count: int
    total_pairs: int
    dispatched_count: int
    completed_count: int
    failed_count: int
    created_at: datetime
    updated_at: datetime
    triggered_by: str | None = None
    schedule_id: str | None = None


class GraiEvalRunCancelResponse(BaseModel):
    eval_run_id: str
    applied: bool
    status: str
    reason: str


class GraiEvalRunProgressResponse(BaseModel):
    eval_run_id: str
    status: str
    terminal_outcome: str | None = None
    prompt_count: int
    case_count: int
    total_pairs: int
    dispatched_count: int
    completed_count: int
    failed_count: int
    progress_fraction: float = 0.0
    updated_at: datetime


GraiEvalResultStatusFilter = Literal["passed", "failed"]
GraiEvalMatrixCellStatus = Literal["passed", "failed", "error", "pending"]


class GraiEvalResultFiltersResponse(BaseModel):
    prompt_id: str | None = None
    assertion_type: str | None = None
    tag: str | None = None
    status: GraiEvalResultStatusFilter | None = None
    destination_index: int | None = None


class GraiEvalAssertionTypeBreakdownResponse(BaseModel):
    assertion_type: str
    total_results: int
    passed_results: int
    failed_results: int


class GraiEvalFailingPromptVariantResponse(BaseModel):
    prompt_id: str
    prompt_label: str
    failure_count: int
    failed_pairs: int


class GraiEvalTagFailureClusterResponse(BaseModel):
    tag: str
    failure_count: int
    failed_pairs: int


class GraiEvalResultListItemResponse(BaseModel):
    eval_result_id: str
    destination_index: int | None = None
    transport_profile_id: str | None = None
    destination_label: str | None = None
    prompt_id: str
    prompt_label: str
    case_id: str
    case_description: str | None = None
    assertion_index: int
    assertion_type: str
    passed: bool
    score: float | None = None
    threshold: float | None = None
    weight: float
    raw_value: str | None = None
    failure_reason: str | None = None
    latency_ms: int | None = None
    tags_json: list[str]
    raw_s3_key: str | None = None
    created_at: datetime


class GraiEvalResultPageResponse(BaseModel):
    eval_run_id: str
    filters: GraiEvalResultFiltersResponse
    items: list[GraiEvalResultListItemResponse]
    next_cursor: str | None = None


class GraiEvalReportResponse(BaseModel):
    eval_run_id: str
    suite_id: str
    status: str
    terminal_outcome: str | None = None
    total_pairs: int
    filters: GraiEvalResultFiltersResponse
    total_results: int
    passed_results: int
    failed_results: int
    assertion_type_breakdown: list[GraiEvalAssertionTypeBreakdownResponse]
    failing_prompt_variants: list[GraiEvalFailingPromptVariantResponse]
    tag_failure_clusters: list[GraiEvalTagFailureClusterResponse]
    exemplar_failures: list[GraiEvalResultListItemResponse]


class GraiEvalMatrixAssertionResultResponse(BaseModel):
    assertion_index: int
    assertion_type: str
    passed: bool
    failure_reason: str | None = None


class GraiEvalMatrixCellResponse(BaseModel):
    destination_index: int
    transport_profile_id: str
    destination_label: str
    status: GraiEvalMatrixCellStatus
    artifact_eval_result_id: str | None = None
    # TODO(36.4): populate from raw_value once the matrix UI slice lands.
    # Always None in the current slice — consumers must open the artifact viewer for response text.
    response_snippet: str | None = None
    latency_ms: int | None = None
    assertion_results: list[GraiEvalMatrixAssertionResultResponse]


class GraiEvalMatrixRowResponse(BaseModel):
    prompt_id: str
    case_id: str
    case_description: str | None = None
    tags_json: list[str]
    cells: list[GraiEvalMatrixCellResponse]


class GraiEvalMatrixPromptGroupResponse(BaseModel):
    prompt_id: str
    prompt_label: str
    prompt_text: str
    rows: list[GraiEvalMatrixRowResponse]


class GraiEvalMatrixDestinationSummaryResponse(BaseModel):
    destination_index: int
    transport_profile_id: str
    label: str
    protocol: str
    pass_rate: float
    total_pairs: int
    passed: int
    failed: int
    errors: int
    avg_latency_ms: float | None = None


class GraiEvalMatrixResponse(BaseModel):
    eval_run_id: str
    suite_id: str
    status: str
    terminal_outcome: str | None = None
    total_pairs: int
    destinations: list[GraiEvalMatrixDestinationSummaryResponse]
    prompt_groups: list[GraiEvalMatrixPromptGroupResponse]


class GraiEvalArtifactResponse(BaseModel):
    prompt_id: str
    case_id: str
    prompt_text: str
    vars_json: dict[str, Any]
    response_text: str
    assertions: list[dict[str, Any]]
