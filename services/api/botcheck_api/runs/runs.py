import logging
from datetime import UTC, datetime, timedelta
from typing import Literal

import structlog
from botcheck_scenarios import (
    ConversationTurn,
    ErrorCode,
    GateResult,
    RunStatus,
    ScoringDimension,
)
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import metrics as api_metrics
from ..audit import write_audit_event
from ..auth import (
    UserContext,
    get_current_user,
    get_service_caller,
    require_editor,
    require_operator,
    require_viewer,
)
from ..capacity import release_sip_slot
from ..config import settings
from ..database import get_db
from ..models import PlaygroundMode, RetentionProfile, RunRow, RunState, RunType
from ..redaction import redact_turn_payload
from ..retention import (
    build_retention_plan,
    delete_report_artifact,
    download_artifact_bytes,
    upload_artifact_bytes,
)
from ..text_normalization import strip_lower_or_none, strip_nonempty, strip_or_none
from ..runs.service import (
    EndReason,
    HeartbeatStatus,
    RunResponse,
    RunScore,
    apply_run_heartbeat,
    append_playground_event,
    append_path_event_dedup,
    build_recording_s3_key,
    build_taken_path_steps,
    create_run_internal,
    deserialize_scores,
    derive_end_reason,
    derive_turn_visit,
    delete_livekit_room,
    is_tts_cache_s3_key,
    iter_live_playground_events,
    livekit_room_exists,
    list_playground_events,
    format_sse_event,
    normalize_branch_snippet,
    normalize_cache_status,
    normalize_scores,
    parse_last_event_id,
    parse_end_reason,
    parse_end_source,
    parse_error_code,
    parse_loop_guard_event_detail,
    parse_recording_format,
    parse_run_state,
    parse_turn_number,
    parse_turn_visit,
    redis_pool_from_request,
    run_effective_max_duration_s,
    run_elapsed_seconds,
    run_last_heartbeat_age_s,
    publish_playground_event,
    serialize_playground_event,
    sip_slot_key_for_run,
    supports_live_playground_pubsub,
    TERMINAL_PLAYGROUND_EVENT,
    transition_run_state,
)

logger = logging.getLogger("botcheck.api.runs")
event_logger = structlog.get_logger("botcheck.api.runs.lifecycle")
router = APIRouter()

_VALID_SCORE_DIMENSIONS: frozenset[str] = frozenset(d.value for d in ScoringDimension)
PLAYGROUND_SYSTEM_PROMPT_MAX_LENGTH = 16_000
PLAYGROUND_PRESET_DESCRIPTION_MAX_LENGTH = 4_000

def _normalize_tool_stubs_payload(
    value: dict[str, object] | None,
) -> dict[str, object] | None:
    if value is None:
        return None
    normalized: dict[str, object] = {}
    for key, stub_value in value.items():
        candidate = str(key).strip()
        if candidate:
            normalized[candidate] = stub_value
    return normalized or None


def _validate_playground_mode_contract(
    *,
    scenario_id: str | None,
    ai_scenario_id: str | None,
    playground_mode: PlaygroundMode,
    transport_profile_id: str | None,
    system_prompt: str | None,
    tool_stubs: dict[str, object] | None,
    exact_one_target: bool,
) -> None:
    target_count = int(bool(scenario_id)) + int(bool(ai_scenario_id))
    if exact_one_target:
        if target_count != 1:
            raise ValueError("Exactly one of scenario_id or ai_scenario_id is required")
    elif target_count == 0:
        raise ValueError("Either scenario_id or ai_scenario_id is required")

    if playground_mode == PlaygroundMode.MOCK:
        if not system_prompt:
            raise ValueError("system_prompt is required for mock playground runs")
        if transport_profile_id:
            raise ValueError("transport_profile_id is not allowed for mock playground runs")
        return
    if playground_mode == PlaygroundMode.DIRECT_HTTP:
        if not transport_profile_id:
            raise ValueError("transport_profile_id is required for direct_http playground runs")
        if system_prompt:
            raise ValueError("system_prompt is not allowed for direct_http playground runs")
        if tool_stubs:
            raise ValueError("tool_stubs are not allowed for direct_http playground runs")


class RunCreate(BaseModel):
    scenario_id: str | None = None
    ai_scenario_id: str | None = None
    transport_profile_id: str | None = None
    trunk_pool_id: str | None = None
    dial_target: str | None = None
    bot_endpoint: str | None = None
    destination_id: str | None = None
    retention_profile: RetentionProfile | None = None
    """Override the scenario's bot endpoint (useful for testing different envs)."""

    @field_validator("scenario_id", "ai_scenario_id", "transport_profile_id", "trunk_pool_id", "dial_target", "bot_endpoint", "destination_id")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return strip_or_none(value)

    @model_validator(mode="after")
    def validate_target_contract(self) -> "RunCreate":
        if self.transport_profile_id and self.trunk_pool_id:
            raise ValueError("trunk_pool_id cannot be combined with transport_profile_id")
        if self.destination_id and self.trunk_pool_id:
            raise ValueError("trunk_pool_id cannot be combined with destination_id")
        if self.trunk_pool_id and not (self.dial_target or self.bot_endpoint):
            raise ValueError("dial_target is required when trunk_pool_id is provided")
        return self


class PlaygroundRunCreate(BaseModel):
    scenario_id: str | None = None
    ai_scenario_id: str | None = None
    playground_mode: PlaygroundMode
    transport_profile_id: str | None = None
    system_prompt: str | None = Field(default=None, max_length=PLAYGROUND_SYSTEM_PROMPT_MAX_LENGTH)
    tool_stubs: dict[str, object] | None = None
    retention_profile: RetentionProfile | None = None

    @field_validator("scenario_id", "ai_scenario_id", "transport_profile_id", "system_prompt")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return strip_or_none(value)

    @field_validator("tool_stubs")
    @classmethod
    def normalize_tool_stubs(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        return _normalize_tool_stubs_payload(value)

    @model_validator(mode="after")
    def validate_mode_contract(self) -> "PlaygroundRunCreate":
        _validate_playground_mode_contract(
            scenario_id=self.scenario_id,
            ai_scenario_id=self.ai_scenario_id,
            playground_mode=self.playground_mode,
            transport_profile_id=self.transport_profile_id,
            system_prompt=self.system_prompt,
            tool_stubs=self.tool_stubs,
            exact_one_target=False,
        )
        return self


class PlaygroundPresetWrite(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=PLAYGROUND_PRESET_DESCRIPTION_MAX_LENGTH)
    scenario_id: str | None = None
    ai_scenario_id: str | None = None
    playground_mode: PlaygroundMode
    transport_profile_id: str | None = None
    system_prompt: str | None = Field(default=None, max_length=PLAYGROUND_SYSTEM_PROMPT_MAX_LENGTH)
    tool_stubs: dict[str, object] | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return strip_nonempty(value, error_message="name is required")

    @field_validator("description", "scenario_id", "ai_scenario_id", "transport_profile_id", "system_prompt")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return strip_or_none(value)

    @field_validator("tool_stubs")
    @classmethod
    def normalize_tool_stubs(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        return _normalize_tool_stubs_payload(value)

    @model_validator(mode="after")
    def validate_mode_contract(self) -> "PlaygroundPresetWrite":
        _validate_playground_mode_contract(
            scenario_id=self.scenario_id,
            ai_scenario_id=self.ai_scenario_id,
            playground_mode=self.playground_mode,
            transport_profile_id=self.transport_profile_id,
            system_prompt=self.system_prompt,
            tool_stubs=self.tool_stubs,
            exact_one_target=True,
        )
        return self


class PlaygroundPresetPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=PLAYGROUND_PRESET_DESCRIPTION_MAX_LENGTH)
    scenario_id: str | None = None
    ai_scenario_id: str | None = None
    playground_mode: PlaygroundMode | None = None
    transport_profile_id: str | None = None
    system_prompt: str | None = Field(default=None, max_length=PLAYGROUND_SYSTEM_PROMPT_MAX_LENGTH)
    tool_stubs: dict[str, object] | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return strip_nonempty(value, error_message="name is required")

    @field_validator("description", "scenario_id", "ai_scenario_id", "transport_profile_id", "system_prompt")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return strip_or_none(value)

    @field_validator("tool_stubs")
    @classmethod
    def normalize_tool_stubs(cls, value: dict[str, object] | None) -> dict[str, object] | None:
        return _normalize_tool_stubs_payload(value)


class PlaygroundPresetSummary(BaseModel):
    preset_id: str
    name: str
    description: str | None = None
    scenario_id: str | None = None
    ai_scenario_id: str | None = None
    playground_mode: PlaygroundMode
    transport_profile_id: str | None = None
    has_tool_stubs: bool = False
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class PlaygroundPresetDetail(PlaygroundPresetSummary):
    system_prompt: str | None = None
    tool_stubs: dict[str, object] | None = None


class PlaygroundExtractToolsRequest(BaseModel):
    system_prompt: str | None = None

    @field_validator("system_prompt")
    @classmethod
    def normalize_system_prompt(cls, value: str | None) -> str | None:
        return strip_or_none(value)


class PlaygroundExtractedTool(BaseModel):
    name: str
    description: str = ""
    parameters: dict[str, object] = Field(default_factory=dict)


class PlaygroundGenerateStubsRequest(BaseModel):
    tools: list[PlaygroundExtractedTool]
    scenario_summary: str = ""

    @field_validator("scenario_summary")
    @classmethod
    def normalize_summary(cls, value: str) -> str:
        # Intentionally not strip_nonempty: blank summary is valid (field defaults to "").
        return value.strip()


class HarnessRunContextResponse(BaseModel):
    run_id: str
    transport_profile_id: str | None = None
    endpoint: str | None = None
    headers: dict[str, object] = Field(default_factory=dict)
    direct_http_config: dict[str, object] = Field(default_factory=dict)
    webrtc_provider: str | None = None
    webrtc_session_mode: str | None = None
    webrtc_session_id: str | None = None
    webrtc_remote_room_name: str | None = None
    webrtc_participant_name: str | None = None
    webrtc_server_url: str | None = None
    webrtc_participant_token: str | None = None
    webrtc_join_timeout_s: int | None = None
    playground_mode: PlaygroundMode | None = None
    playground_system_prompt: str | None = None
    playground_tool_stubs: dict[str, object] | None = None


class PlaygroundEventCreate(BaseModel):
    event_type: str
    payload: dict[str, object] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def normalize_event_type(cls, value: str) -> str:
        return strip_nonempty(value, error_message="event_type is required")


class PlaygroundEventResponse(BaseModel):
    run_id: str
    sequence_number: int
    event_type: str
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class ScheduledRunCreate(RunCreate):
    schedule_id: str
    triggered_by: str = "scheduler"


class GateResponse(BaseModel):
    run_id: str
    gate_result: GateResult
    overall_status: RunStatus | None = None
    failed_dimensions: list[str] = Field(default_factory=list)
    summary: str = ""


class RetentionSweepRequest(BaseModel):
    dry_run: bool = False
    limit: int = Field(default=500, ge=1, le=5000)


class RetentionSweepResponse(BaseModel):
    dry_run: bool
    checked: int
    mutated: int
    artifacts_deleted: int
    artifacts_failed: int


class RunReaperSweepRequest(BaseModel):
    dry_run: bool = False
    limit: int = Field(default=200, ge=1, le=5000)
    grace_s: float = Field(default=60.0, ge=0.0, le=3600.0)


class RunReaperSweepResponse(BaseModel):
    dry_run: bool
    checked: int
    overdue: int
    heartbeat_stale: int
    closed: int
    room_active: int
    room_missing: int
    livekit_errors: int
    sip_slots_released: int
    close_errors: int


class RunHeartbeatRequest(BaseModel):
    sent_at: datetime
    seq: int = Field(ge=1)
    turn_number: int | None = Field(default=None, ge=1)
    listener_state: str | None = None

    @field_validator("sent_at")
    @classmethod
    def validate_sent_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("sent_at must include timezone information")
        if value.utcoffset() != timedelta(0):
            raise ValueError("sent_at must be UTC (Z)")
        return value.astimezone(UTC)

    @field_validator("listener_state")
    @classmethod
    def validate_listener_state(cls, value: str | None) -> str | None:
        # Intentionally not just strip_or_none: listener_state is lowercased and still
        # enforces its max-length contract after whitespace collapse.
        candidate = strip_lower_or_none(value)
        if candidate is None:
            return None
        if len(candidate) > 64:
            raise ValueError("listener_state must be <= 64 characters")
        return candidate


class RunHeartbeatResponse(BaseModel):
    ok: bool = True
    status: Literal["updated", "duplicate_or_stale", "ignored_terminal"]
    state: RunState
    last_heartbeat_at: datetime | None = None
    last_heartbeat_seq: int | None = None


class RecordingUploadResponse(BaseModel):
    ok: bool
    recording_s3_key: str | None = None
    skipped_reason: str | None = None


class RunPatch(BaseModel):
    state: str | None = None
    gate_result: str | None = None
    overall_status: str | None = None
    failed_dimensions: list[str] | None = None
    error_code: str | None = None
    summary: str | None = None
    scores: dict[str, float | RunScore] | None = None
    findings: list[dict[str, object]] | None = None
    report_s3_key: str | None = None
    cost_pence: int | None = Field(default=None, ge=0)

    @field_validator("scores")
    @classmethod
    def validate_score_dimensions(
        cls, v: dict[str, float | RunScore] | None
    ) -> dict[str, float | RunScore] | None:
        if v is None:
            return v
        invalid = set(v.keys()) - _VALID_SCORE_DIMENSIONS
        if invalid:
            raise ValueError(f"Unknown scoring dimension(s): {sorted(invalid)}")
        return v


class RunOperatorActionRequest(BaseModel):
    reason: str | None = None


class RunOperatorActionResponse(BaseModel):
    run_id: str
    applied: bool
    state: str
    reason: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Subrouters
# ---------------------------------------------------------------------------

# NOTE: import order matters because split modules alias symbols from this
# module (models/helpers/imported services) for backward compatibility.
from . import runs_artifacts as _runs_artifacts
from . import runs_events as _runs_events
from . import runs_lifecycle as _runs_lifecycle
from . import runs_maintenance as _runs_maintenance

router.include_router(_runs_maintenance.router)
router.include_router(_runs_lifecycle.router)
router.include_router(_runs_events.router)
router.include_router(_runs_artifacts.router)
