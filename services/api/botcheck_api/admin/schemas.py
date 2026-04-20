from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class AdminUserSummaryResponse(BaseModel):
    user_id: str
    tenant_id: str
    email: str
    role: str
    is_active: bool
    totp_enabled: bool
    failed_login_attempts: int
    locked_until: datetime | None
    sessions_invalidated_at: datetime | None
    last_login_at: datetime | None
    active_session_count: int
    created_at: datetime
    updated_at: datetime


class AdminUserDetailResponse(AdminUserSummaryResponse):
    pass


class AdminUsersListResponse(BaseModel):
    items: list[AdminUserSummaryResponse]
    total: int
    limit: int
    offset: int


class AdminUserCreateRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    role: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    is_active: bool = True


class AdminUserPatchRequest(BaseModel):
    email: str | None = Field(default=None, min_length=5, max_length=320)
    role: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_non_empty_patch(self) -> "AdminUserPatchRequest":
        if self.email is None and self.role is None:
            raise ValueError("At least one field must be provided")
        return self


class AdminUserPasswordResetRequest(BaseModel):
    password: str = Field(min_length=8, max_length=256)


class AdminUserActionResponse(BaseModel):
    user_id: str
    applied: bool = True
    revoked_sessions: int = 0


class AdminUserReset2FAResponse(BaseModel):
    user_id: str
    revoked_sessions: int
    recovery_codes_invalidated: int


class TenantQuotaConfigResponse(BaseModel):
    max_concurrent_runs: int
    max_runs_per_day: int
    max_schedules: int
    max_scenarios: int
    max_packs: int


class AdminTenantSummaryResponse(BaseModel):
    tenant_id: str
    slug: str
    display_name: str
    feature_overrides: dict[str, bool | int | float] = Field(default_factory=dict)
    quota_config: dict[str, int] = Field(default_factory=dict)
    effective_quotas: TenantQuotaConfigResponse
    total_users: int
    active_users: int
    scenario_count: int
    schedule_count: int
    pack_count: int
    active_run_count: int
    suspended_at: datetime | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AdminTenantDetailResponse(AdminTenantSummaryResponse):
    pass


class AdminTenantsListResponse(BaseModel):
    items: list[AdminTenantSummaryResponse]
    total: int
    limit: int
    offset: int


class AdminTenantCreateRequest(BaseModel):
    tenant_id: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    feature_overrides: dict[str, bool | int | float] = Field(default_factory=dict)
    quota_config: dict[str, int] = Field(default_factory=dict)


class AdminTenantPatchRequest(BaseModel):
    slug: str | None = Field(default=None, min_length=1, max_length=255)
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    feature_overrides: dict[str, bool | int | float] | None = None
    quota_config: dict[str, int] | None = None

    @model_validator(mode="after")
    def validate_non_empty_patch(self) -> "AdminTenantPatchRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class AdminTenantActionResponse(BaseModel):
    tenant_id: str
    applied: bool = True
    suspended_at: datetime | None = None
    deleted_at: datetime | None = None


class AdminAuditEventDetailResponse(BaseModel):
    event_id: str
    tenant_id: str
    actor_id: str
    actor_type: str
    action: str
    resource_type: str
    resource_id: str
    detail: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class AdminAuditEventsListResponse(BaseModel):
    items: list[AdminAuditEventDetailResponse]
    total: int
    limit: int
    offset: int


class AdminSIPTrunkDetailResponse(BaseModel):
    trunk_id: str
    name: str | None
    provider_name: str | None
    address: str | None
    transport: str | None
    numbers: list[str] = Field(default_factory=list)
    metadata_json: dict[str, object] = Field(default_factory=dict)
    is_active: bool
    last_synced_at: datetime
    created_at: datetime
    updated_at: datetime


class AdminSIPTrunksListResponse(BaseModel):
    items: list[AdminSIPTrunkDetailResponse]
    total: int


class AdminSIPTrunkPoolMemberResponse(BaseModel):
    trunk_id: str
    name: str | None = None
    provider_name: str | None = None
    is_active: bool
    priority: int


class AdminSIPTrunkPoolAssignmentResponse(BaseModel):
    tenant_id: str
    tenant_label: str
    is_default: bool
    is_active: bool
    max_channels: int | None = None
    reserved_channels: int | None = None


class AdminSIPTrunkPoolAssignmentQuotaMixin(BaseModel):
    max_channels: int | None = Field(default=None, ge=1)
    reserved_channels: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_channel_limits(self):
        if (
            self.max_channels is not None
            and self.reserved_channels is not None
            and self.reserved_channels > self.max_channels
        ):
            raise ValueError("reserved_channels must be less than or equal to max_channels")
        return self


class AdminSIPTrunkPoolDetailResponse(BaseModel):
    trunk_pool_id: str
    name: str
    provider_name: str
    selection_policy: str
    is_active: bool
    members: list[AdminSIPTrunkPoolMemberResponse] = Field(default_factory=list)
    assignments: list[AdminSIPTrunkPoolAssignmentResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AdminSIPTrunkPoolsListResponse(BaseModel):
    items: list[AdminSIPTrunkPoolDetailResponse]
    total: int


class AdminSIPTrunkPoolCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    provider_name: str = Field(min_length=1, max_length=255)


class AdminSIPTrunkPoolPatchRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_non_empty_patch(self) -> "AdminSIPTrunkPoolPatchRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        return self


class AdminSIPTrunkPoolMemberCreateRequest(BaseModel):
    trunk_id: str = Field(min_length=1, max_length=255)
    priority: int = Field(default=100, ge=0, le=10000)


class AdminSIPTrunkPoolAssignmentCreateRequest(AdminSIPTrunkPoolAssignmentQuotaMixin):
    tenant_id: str = Field(min_length=2, max_length=255)
    tenant_label: str | None = Field(default=None, max_length=255)
    is_default: bool = False


class AdminSIPTrunkPoolAssignmentPatchRequest(AdminSIPTrunkPoolAssignmentQuotaMixin):
    tenant_label: str | None = Field(default=None, max_length=255)
    is_default: bool | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_non_empty_patch(self) -> "AdminSIPTrunkPoolAssignmentPatchRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "is_default" in self.model_fields_set and self.is_default is None:
            raise ValueError("is_default must be true or false, not null")
        if "is_active" in self.model_fields_set and self.is_active is None:
            raise ValueError("is_active must be true or false, not null")
        return self


class AdminSIPSyncResponse(BaseModel):
    synced: bool = True
    total: int
    active: int


class AdminSystemHealthComponentResponse(BaseModel):
    status: str


class AdminSystemProviderHealthResponse(BaseModel):
    configured: bool
    key_location: str = "api"  # "api" = key required here; "agent" = key lives in agent service


class AdminSystemHealthResponse(BaseModel):
    database: AdminSystemHealthComponentResponse
    redis: AdminSystemHealthComponentResponse
    livekit: AdminSystemHealthComponentResponse
    providers: dict[str, AdminSystemProviderHealthResponse]
    timestamp: datetime


class AdminSystemConfigResponse(BaseModel):
    config: dict[str, object]


class AdminSystemFeatureFlagsPatchRequest(BaseModel):
    feature_flags: dict[str, bool | int | float]


class AdminSystemFeatureFlagsResponse(BaseModel):
    feature_flags: dict[str, bool]
    updated_at: datetime


class AdminSystemQuotaPatchRequest(BaseModel):
    quota_defaults: dict[str, int]


class AdminSystemQuotaResponse(BaseModel):
    quota_defaults: dict[str, int]
    updated_at: datetime
