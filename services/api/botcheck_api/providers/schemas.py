from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..text_normalization import strip_nonempty, strip_or_none
from .usage_service import provider_quota_metric_names


class ProviderAvailabilitySummaryResponse(BaseModel):
    provider_id: str
    vendor: str
    model: str
    capability: str
    runtime_scopes: list[str] = Field(default_factory=list)
    credential_source: str
    configured: bool
    availability_status: str
    supports_tenant_credentials: bool


class ProviderAvailableListResponse(BaseModel):
    items: list[ProviderAvailabilitySummaryResponse] = Field(default_factory=list)


class ProviderRuntimeContextRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    runtime_scope: Literal["agent", "judge", "api"]
    tts_voice: str | None = None
    stt_provider: str | None = None
    stt_model: str | None = None
    provider_bindings: list["ProviderRuntimeBindingRequest"] = Field(default_factory=list)


class ProviderRuntimeBindingRequest(BaseModel):
    capability: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)
    vendor: str | None = Field(default=None, min_length=1, max_length=64)


class ProviderRuntimeBindingResponse(BaseModel):
    capability: str
    vendor: str
    model: str
    provider_id: str | None = None
    credential_source: str
    availability_status: str
    secret_fields: dict[str, str] = Field(default_factory=dict)


class ProviderRuntimeContextResponse(BaseModel):
    tenant_id: str
    runtime_scope: Literal["agent", "judge", "api"]
    feature_flags: dict[str, bool] = Field(default_factory=dict)
    tts: ProviderRuntimeBindingResponse | None = None
    stt: ProviderRuntimeBindingResponse | None = None
    providers: list[ProviderRuntimeBindingResponse] = Field(default_factory=list)


class ProviderUsageWriteRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    provider_id: str = Field(min_length=3, max_length=128)
    usage_key: str = Field(min_length=1, max_length=255)
    runtime_scope: Literal["agent", "judge", "api"]
    capability: str = Field(min_length=1, max_length=64)
    run_id: str | None = None
    eval_run_id: str | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    audio_seconds: float = Field(default=0.0, ge=0.0)
    characters: int = Field(default=0, ge=0)
    sip_minutes: float = Field(default=0.0, ge=0.0)
    request_count: int = Field(default=1, ge=0)


class ProviderUsageWriteResponse(BaseModel):
    stored: bool
    ledger_id: str | None = None


class TenantProviderUsageSummaryResponse(BaseModel):
    provider_id: str
    vendor: str
    model: str
    capability: str
    runtime_scopes: list[str] = Field(default_factory=list)
    last_recorded_at: datetime | None = None
    input_tokens_24h: int = 0
    output_tokens_24h: int = 0
    audio_seconds_24h: float = 0.0
    characters_24h: int = 0
    sip_minutes_24h: float = 0.0
    request_count_24h: int = 0
    calculated_cost_microcents_24h: int | None = None


class TenantProviderUsageListResponse(BaseModel):
    window_start: datetime
    window_end: datetime
    items: list[TenantProviderUsageSummaryResponse] = Field(default_factory=list)


class TenantProviderQuotaMetricResponse(BaseModel):
    metric: str
    limit_per_day: int
    used_24h: float
    remaining_24h: float
    soft_limit_pct: int
    percent_used: float
    status: str
    soft_limit_reached: bool
    hard_limit_reached: bool


class TenantProviderQuotaSummaryResponse(BaseModel):
    provider_id: str
    vendor: str
    model: str
    capability: str
    metrics: list[TenantProviderQuotaMetricResponse] = Field(default_factory=list)


class TenantProviderQuotaListResponse(BaseModel):
    window_start: datetime
    window_end: datetime
    items: list[TenantProviderQuotaSummaryResponse] = Field(default_factory=list)


class ProviderCostMetadataResponse(BaseModel):
    cost_per_input_token_microcents: int | None = None
    cost_per_output_token_microcents: int | None = None
    cost_per_audio_second_microcents: int | None = None
    cost_per_character_microcents: int | None = None
    cost_per_request_microcents: int | None = None


class ProviderCredentialStateResponse(BaseModel):
    credential_source: str
    validation_status: str
    validated_at: datetime | None = None
    validation_error: str | None = None
    updated_at: datetime | None = None
    has_stored_secret: bool = False


class AdminProviderAssignedTenantResponse(BaseModel):
    tenant_id: str
    tenant_display_name: str
    enabled: bool


class AdminProviderSummaryResponse(BaseModel):
    provider_id: str
    vendor: str
    model: str
    capability: str
    label: str | None = None
    user_created: bool = False
    runtime_scopes: list[str] = Field(default_factory=list)
    supports_tenant_credentials: bool
    supports_platform_credentials: bool
    credential_source: str
    configured: bool
    available: bool
    availability_status: str
    tenant_assignment_count: int
    assigned_tenant: AdminProviderAssignedTenantResponse | None = None
    cost_metadata: ProviderCostMetadataResponse
    platform_credential: ProviderCredentialStateResponse | None = None


class AdminProvidersListResponse(BaseModel):
    items: list[AdminProviderSummaryResponse] = Field(default_factory=list)
    total: int


class AdminProviderEnvImportItemResponse(BaseModel):
    provider_id: str
    status: str
    detail: str


class AdminProviderEnvImportResponse(BaseModel):
    imported_count: int = 0
    skipped_count: int = 0
    items: list[AdminProviderEnvImportItemResponse] = Field(default_factory=list)


class AdminProviderUsageResponse(BaseModel):
    window_start: datetime
    window_end: datetime
    item: TenantProviderUsageSummaryResponse


class AdminProviderQuotaResponse(BaseModel):
    window_start: datetime
    window_end: datetime
    item: TenantProviderQuotaSummaryResponse


class AdminProviderCredentialWriteRequest(BaseModel):
    secret_fields: dict[str, str] = Field(default_factory=dict)

    @field_validator("secret_fields")
    @classmethod
    def _normalize_secret_fields(cls, value: dict[str, str]) -> dict[str, str]:
        # Intentionally not using strip_nonempty: iterates both dict keys and values
        # with context-specific error messages per entry; the shared helper only
        # handles scalar strings and cannot express the key vs. value distinction here.
        normalized: dict[str, str] = {}
        for key, raw in value.items():
            candidate_key = str(key).strip()
            candidate_value = str(raw).strip()
            if not candidate_key:
                raise ValueError("secret_fields keys must not be blank")
            if not candidate_value:
                raise ValueError(f"secret_fields['{candidate_key}'] must not be blank")
            normalized[candidate_key] = candidate_value
        if not normalized:
            raise ValueError("secret_fields must not be empty")
        return normalized


class AdminProviderCredentialMutationResponse(BaseModel):
    provider_id: str
    credential_source: str
    validation_status: str
    validated_at: datetime | None = None
    validation_error: str | None = None
    updated_at: datetime | None = None


class AdminProviderAssignmentResponse(BaseModel):
    tenant_id: str
    provider_id: str
    tenant_display_name: str
    enabled: bool
    is_default: bool
    effective_credential_source: str
    updated_at: datetime


class AdminProviderAssignmentsListResponse(BaseModel):
    items: list[AdminProviderAssignmentResponse] = Field(default_factory=list)
    total: int


class AdminProviderQuotaPolicyResponse(BaseModel):
    quota_policy_id: str
    tenant_id: str
    provider_id: str
    tenant_display_name: str
    metric: str
    limit_per_day: int
    soft_limit_pct: int
    updated_at: datetime


class AdminProviderQuotaPoliciesListResponse(BaseModel):
    items: list[AdminProviderQuotaPolicyResponse] = Field(default_factory=list)
    total: int


class AdminProviderQuotaPolicyWriteRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=255)
    metric: str = Field(min_length=1, max_length=32)
    limit_per_day: int = Field(ge=0)
    soft_limit_pct: int = Field(default=80, ge=0, le=100)

    @field_validator("metric")
    @classmethod
    def _normalize_metric(cls, value: str) -> str:
        candidate = strip_nonempty(value, error_message="metric must not be blank")
        if candidate not in provider_quota_metric_names():
            raise ValueError(
                f"Unsupported provider quota metric: {candidate!r}. "
                f"Allowed values: {', '.join(sorted(provider_quota_metric_names()))}"
            )
        return candidate


class AdminProviderQuotaPolicyMutationResponse(BaseModel):
    provider_id: str
    tenant_id: str
    metric: str
    applied: bool = True


class AdminTenantProviderAssignRequest(BaseModel):
    provider_id: str = Field(min_length=3, max_length=128)
    is_default: bool = False


class AdminTenantProviderAssignmentMutationResponse(BaseModel):
    tenant_id: str
    provider_id: str
    enabled: bool
    is_default: bool


class AdminProviderAssignRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=255)


class AdminProviderCreateRequest(BaseModel):
    capability: str = Field(min_length=1, max_length=32)
    vendor: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)
    label: str | None = Field(default=None, max_length=255)
    api_key: str = Field(min_length=1, max_length=2048)

    @field_validator("label")
    @classmethod
    def _normalize_label(cls, value: str | None) -> str | None:
        return strip_or_none(value)

    @field_validator("capability")
    @classmethod
    def _validate_capability(cls, value: str) -> str:
        allowed = {"llm", "tts", "stt", "sip", "judge"}
        normalized = strip_nonempty(value, error_message="capability must not be blank").lower()
        if normalized not in allowed:
            raise ValueError(f"capability must be one of: {', '.join(sorted(allowed))}")
        return normalized

    @field_validator("vendor")
    @classmethod
    def _validate_vendor(cls, value: str) -> str:
        return strip_nonempty(value, error_message="vendor must not be blank").lower()

    @field_validator("model")
    @classmethod
    def _validate_model(cls, value: str) -> str:
        return strip_nonempty(value, error_message="model must not be blank")

    @field_validator("api_key")
    @classmethod
    def _validate_api_key(cls, value: str) -> str:
        return strip_nonempty(value, error_message="api_key must not be blank")


class AdminProviderUpdateRequest(BaseModel):
    label: str | None = Field(default=None, max_length=255)

    @field_validator("label")
    @classmethod
    def _normalize_label(cls, value: str | None) -> str | None:
        return strip_or_none(value)


class AdminProviderDeleteResponse(BaseModel):
    provider_id: str
    deleted: bool = True
