"""Pydantic schemas for the scenarios feature."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .service import ValidationWarning


class ScenarioCreate(BaseModel):
    yaml_content: str
    """Raw YAML of the scenario definition."""


class ScenarioSourceResponse(BaseModel):
    scenario_id: str
    yaml_content: str


class ScenarioResponse(BaseModel):
    id: str
    name: str
    namespace: str | None = None
    type: str
    scenario_kind: Literal["graph", "ai"] = "graph"
    description: str
    version_hash: str
    cache_status: str = "cold"
    cache_updated_at: datetime | None = None
    tags: list[str]
    turns: int
    created_at: datetime | None = None


class ScenarioValidationError(BaseModel):
    field: str
    message: str


class ScenarioValidationResult(BaseModel):
    valid: bool
    errors: list[ScenarioValidationError] = Field(default_factory=list)
    warnings: list[ValidationWarning] = Field(default_factory=list)
    scenario_id: str | None = None
    turns: int | None = None
    path_summary: str | None = None


class ScenarioCacheRebuildResponse(BaseModel):
    scenario_id: str
    cache_status: str
    queue: str
    enqueued: bool


class ScenarioCacheSyncRequest(BaseModel):
    tenant_id: str
    scenario_version_hash: str
    cache_status: Literal["cold", "partial", "warm"]
    cached_turns: int = 0
    skipped_turns: int = 0
    failed_turns: int = 0
    manifest_s3_key: str | None = None


class ScenarioCacheSyncResponse(BaseModel):
    scenario_id: str
    applied: bool
    cache_status: str
    reason: str


class ScenarioCacheTurnState(BaseModel):
    turn_id: str
    status: Literal["cached", "skipped", "failed", "unknown"]
    key: str | None = None


class ScenarioCacheStateResponse(BaseModel):
    scenario_id: str
    scenario_version_hash: str | None = None
    cache_status: Literal["warm", "warming", "partial", "cold"] = "cold"
    cached_turns: int = 0
    skipped_turns: int = 0
    failed_turns: int = 0
    total_harness_turns: int = 0
    updated_at: str | None = None
    bucket_name: str | None = None
    turn_states: list[ScenarioCacheTurnState] = []


class AIPersonaSummaryResponse(BaseModel):
    persona_id: str
    name: str
    display_name: str
    avatar_url: str | None = None
    backstory_summary: str | None = None
    style: str | None = None
    voice: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AIPersonaUpsertRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    avatar_url: str | None = Field(default=None, max_length=512)
    backstory_summary: str | None = Field(default=None, max_length=2000)
    system_prompt: str = Field(min_length=1, max_length=12000)
    style: str | None = Field(default=None, max_length=128)
    voice: str | None = Field(default=None, max_length=128)
    is_active: bool = True


class AIPersonaDetailResponse(AIPersonaSummaryResponse):
    system_prompt: str


class AIScenarioSummaryResponse(BaseModel):
    ai_scenario_id: str
    scenario_id: str
    name: str
    namespace: str | None = None
    persona_id: str
    scenario_brief: str = ""
    scenario_facts: dict[str, Any] = Field(default_factory=dict)
    evaluation_objective: str = ""
    opening_strategy: Literal["wait_for_bot_greeting", "caller_opens"] = "wait_for_bot_greeting"
    is_active: bool = True
    scoring_profile: str | None = None
    dataset_source: str | None = None
    record_count: int = 0
    created_at: datetime
    updated_at: datetime


class AIScenarioUpsertRequest(BaseModel):
    ai_scenario_id: str | None = Field(default=None, min_length=1, max_length=255)
    scenario_id: str = Field(min_length=1, max_length=255)
    persona_id: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=255)
    namespace: str | None = Field(default=None, max_length=255)
    scenario_brief: str | None = Field(default=None, max_length=20000)
    scenario_facts: dict[str, Any] = Field(default_factory=dict)
    evaluation_objective: str | None = Field(default=None, max_length=20000)
    opening_strategy: Literal["wait_for_bot_greeting", "caller_opens"] = "wait_for_bot_greeting"
    is_active: bool = True
    scoring_profile: str | None = Field(default=None, max_length=128)
    dataset_source: str | None = Field(default=None, max_length=255)
    config: dict[str, Any] = Field(default_factory=dict)


class AIScenarioDetailResponse(AIScenarioSummaryResponse):
    config: dict[str, Any] = Field(default_factory=dict)


class AIScenarioRecordResponse(BaseModel):
    record_id: str
    ai_scenario_id: str
    order_index: int
    input_text: str
    expected_output: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AIScenarioRecordUpsertRequest(BaseModel):
    order_index: int | None = Field(default=None, ge=1)
    input_text: str = Field(min_length=1, max_length=12000)
    expected_output: str = Field(min_length=1, max_length=12000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class GenerateRequest(BaseModel):
    target_system_prompt: str = Field(max_length=8000)
    steering_prompt: str = Field(default="", max_length=2000)
    user_objective: str = Field(max_length=500)
    count: int = Field(ge=1, le=10)


class GeneratedScenario(BaseModel):
    yaml: str
    name: str
    type: str
    technique: str
    turns: int


class GenerateJobStatus(BaseModel):
    job_id: str
    status: Literal["pending", "running", "partial", "complete", "failed"]
    count_requested: int
    count_succeeded: int
    scenarios: list[GeneratedScenario]
    errors: list[str] = Field(default_factory=list)
    created_at: str
    completed_at: str | None = None


class GenerateStartResponse(BaseModel):
    job_id: str
