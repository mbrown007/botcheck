"""Shared run service enums, response models, and typed tuples."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, NamedTuple

from botcheck_scenarios import ConversationTurn
from pydantic import BaseModel, Field

from ..models import PlaygroundMode, RetentionProfile, RunState, RunType


class EndReason(str, Enum):
    EXPLICIT_TERMINATION_REQUEST = "explicit_termination_request"
    SERVICE_NOT_AVAILABLE = "service_not_available"
    CUSTOMER_DECLINED_SERVICE = "customer_declined_service"
    HARNESS_SAFETY_ABORT = "harness_safety_abort"
    PER_TURN_LOOP_LIMIT = "per_turn_loop_limit"
    MAX_TURNS_REACHED = "max_turns_reached"
    MAX_DURATION_EXCEEDED = "max_duration_exceeded"
    TIMEOUT_ORPHAN = "timeout_orphan"
    TIMEOUT = "timeout"


class HeartbeatStatus(str, Enum):
    UPDATED = "updated"
    DUPLICATE_OR_STALE = "duplicate_or_stale"
    IGNORED_TERMINAL = "ignored_terminal"


class RunScore(BaseModel):
    metric_type: Literal["score", "flag"] = "score"
    score: float | None = None
    passed: bool | None = None
    status: str | None = None
    threshold: float | None = None
    gate: bool | None = None
    findings: list[dict[str, object]] = Field(default_factory=list)
    reasoning: str = ""


class RunResponse(BaseModel):
    run_id: str
    scenario_id: str
    state: RunState
    run_type: RunType = RunType.STANDARD
    playground_mode: PlaygroundMode | None = None
    livekit_room: str | None = None
    trigger_source: str = "manual"
    schedule_id: str | None = None
    triggered_by: str | None = None
    transport: str = "none"
    tts_cache_status_at_start: Literal["warm", "warming", "partial", "cold"] | None = None
    destination_id_at_start: str | None = None
    transport_profile_id_at_start: str | None = None
    dial_target_at_start: str | None = None
    capacity_scope_at_start: str | None = None
    capacity_limit_at_start: int | None = None
    retention_profile: RetentionProfile = RetentionProfile.STANDARD
    created_at: datetime | None = None
    gate_result: str | None = None
    failed_dimensions: list[str] = Field(default_factory=list)
    error_code: str | None = None
    end_reason: str | None = None
    end_source: str | None = None
    report_s3_key: str | None = None
    recording_s3_key: str | None = None
    summary: str = ""
    cost_pence: int | None = None
    scores: dict[str, RunScore] = Field(default_factory=dict)
    findings: list[dict[str, object]] = Field(default_factory=list)
    events: list[dict[str, object]] = Field(default_factory=list)
    conversation: list[ConversationTurn] = Field(default_factory=list)


class ResolvedRunTarget(NamedTuple):
    destination_id: str | None
    transport_profile_id: str | None
    protocol: str
    endpoint: str
    dial_target: str
    headers: dict[str, object]
    direct_http_config: dict[str, object] | None
    webrtc_config: dict[str, object] | None
    caller_id: str | None
    trunk_id: str | None
    trunk_pool_id: str | None
    capacity_scope: str
    capacity_limit: int
