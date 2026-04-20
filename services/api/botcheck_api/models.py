"""SQLAlchemy 2.x ORM models for BotCheck API."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RunState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    JUDGING = "judging"
    COMPLETE = "complete"
    FAILED = "failed"
    ERROR = "error"


class RetentionProfile(str, Enum):
    EPHEMERAL = "ephemeral"
    STANDARD = "standard"
    COMPLIANCE = "compliance"
    NO_AUDIO = "no_audio"


class CacheStatus(str, Enum):
    COLD = "cold"
    WARMING = "warming"
    PARTIAL = "partial"
    WARM = "warm"


class PackRunState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScheduleTargetType(str, Enum):
    SCENARIO = "scenario"
    PACK = "pack"


class RunType(str, Enum):
    STANDARD = "standard"
    PLAYGROUND = "playground"


class PlaygroundMode(str, Enum):
    MOCK = "mock"
    DIRECT_HTTP = "direct_http"


class DestinationProtocol(str, Enum):
    SIP = "sip"
    HTTP = "http"
    WEBRTC = "webrtc"
    MOCK = "mock"


class ScenarioKind(str, Enum):
    GRAPH = "graph"
    AI = "ai"


class GraiAssertionType(str, Enum):
    CONTAINS = "contains"
    CONTAINS_ALL = "contains-all"
    CONTAINS_ANY = "contains-any"
    ICONTAINS = "icontains"
    ICONTAINS_ALL = "icontains-all"
    ICONTAINS_ANY = "icontains-any"
    EQUALS = "equals"
    STARTS_WITH = "starts-with"
    REGEX = "regex"
    IS_JSON = "is-json"
    WORD_COUNT = "word-count"
    LEVENSHTEIN = "levenshtein"
    LATENCY = "latency"
    IS_REFUSAL = "is-refusal"
    LLM_RUBRIC = "llm-rubric"
    FACTUALITY = "factuality"
    MODEL_GRADED_CLOSED_QA = "model-graded-closedqa"
    ANSWER_RELEVANCE = "answer-relevance"


class GraiEvalRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GraiEvalRunTerminalOutcome(str, Enum):
    PASSED = "passed"
    ASSERTION_FAILED = "assertion_failed"
    EXECUTION_FAILED = "execution_failed"
    CANCELLED = "cancelled"


class ScenarioRow(Base):
    __tablename__ = "scenarios"
    __table_args__ = (
        CheckConstraint(
            "scenario_kind IN ('graph', 'ai')",
            name="ck_scenarios_kind",
        ),
        Index("ix_scenarios_tenant_namespace", "tenant_id", "namespace"),
    )

    scenario_id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, default="default")
    scenario_kind: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ScenarioKind.GRAPH.value,
    )
    version_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    namespace: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    yaml_content: Mapped[str] = mapped_column(Text, nullable=False)
    cache_status: Mapped[str] = mapped_column(String(16), nullable=False, default=CacheStatus.COLD.value)
    cache_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


class AIPersonaRow(Base):
    __tablename__ = "ai_personas"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_ai_personas_tenant_name"),
    )

    persona_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    backstory_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    style: Mapped[str | None] = mapped_column(String(128), nullable=True)
    voice: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class AIScenarioRow(Base):
    __tablename__ = "ai_scenarios"
    __table_args__ = (
        Index("ix_ai_scenarios_tenant_namespace", "tenant_id", "namespace"),
    )

    scenario_id: Mapped[str] = mapped_column(String, primary_key=True)
    ai_scenario_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, default="")
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    namespace: Mapped[str | None] = mapped_column(String(255), nullable=True)
    persona_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scenario_brief: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scenario_facts: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    evaluation_objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    opening_strategy: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="wait_for_bot_greeting",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    scoring_profile: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dataset_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class AIScenarioRecordRow(Base):
    __tablename__ = "ai_scenario_records"
    __table_args__ = (
        UniqueConstraint("scenario_id", "order_index", name="uq_ai_scenario_records_order"),
    )

    record_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    expected_output: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class RunRow(Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, default="default")
    state: Mapped[str] = mapped_column(String(64), nullable=False, default="pending")
    run_type: Mapped[str] = mapped_column(String(16), nullable=False, default=RunType.STANDARD.value)
    playground_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    playground_system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    playground_tool_stubs: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    livekit_room: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    trigger_source: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    schedule_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pack_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    triggered_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transport: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    sip_slot_held: Mapped[bool] = mapped_column(nullable=False, default=False)
    tts_cache_status_at_start: Mapped[str | None] = mapped_column(String(16), nullable=True)
    destination_id_at_start: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transport_profile_id_at_start: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dial_target_at_start: Mapped[str | None] = mapped_column(String(512), nullable=True)
    direct_http_headers_at_start: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    direct_http_config_at_start: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    webrtc_config_at_start: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    capacity_scope_at_start: Mapped[str | None] = mapped_column(String(128), nullable=True)
    capacity_limit_at_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retention_profile: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RetentionProfile.STANDARD.value
    )
    run_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_duration_s_at_start: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # JSONB on PostgreSQL (via migration 0002); JSON/TEXT on SQLite for tests.
    # SQLAlchemy's JSON type handles Python ↔ JSON serde automatically —
    # application code works with plain lists, no manual json.loads/dumps needed.
    conversation: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    failed_dimensions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    scores: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    findings: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    events: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)

    gate_result: Mapped[str | None] = mapped_column(String(64), nullable=True)
    overall_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    end_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    end_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cost_pence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    report_s3_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    recording_s3_key: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class PlaygroundEventRow(Base):
    __tablename__ = "playground_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence_number", name="uq_playground_events_run_sequence"),
    )

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True, default="default")
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


class PlaygroundPresetRow(Base):
    __tablename__ = "playground_presets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_playground_presets_tenant_name"),
        CheckConstraint(
            "(scenario_id IS NULL) != (ai_scenario_id IS NULL)",
            name="ck_playground_presets_exactly_one_target",
        ),
        CheckConstraint(
            "playground_mode IN ('mock', 'direct_http')",
            name="ck_playground_presets_mode",
        ),
        CheckConstraint(
            "("
            "(playground_mode = 'mock' AND system_prompt IS NOT NULL AND transport_profile_id IS NULL) "
            "OR "
            "(playground_mode = 'direct_http' AND transport_profile_id IS NOT NULL AND system_prompt IS NULL AND tool_stubs IS NULL)"
            ")",
            name="ck_playground_presets_mode_contract",
        ),
        Index("ix_playground_presets_tenant_updated", "tenant_id", "updated_at"),
    )

    preset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scenario_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    ai_scenario_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    playground_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    transport_profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_stubs: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class ScheduleRow(Base):
    __tablename__ = "schedules"
    __table_args__ = (
        CheckConstraint(
            "((target_type = 'scenario' AND scenario_id IS NOT NULL AND pack_id IS NULL) OR "
            "(target_type = 'pack' AND pack_id IS NOT NULL AND scenario_id IS NULL))",
            name="ck_schedules_target_xor",
        ),
    )

    schedule_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ScheduleTargetType.SCENARIO.value
    )
    scenario_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pack_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cron_expr: Mapped[str] = mapped_column(String(128), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_run_outcome: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retry_on_failure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    misfire_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="skip")
    config_overrides: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class SIPTrunkRow(Base):
    __tablename__ = "sip_trunks"

    trunk_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transport: Mapped[str | None] = mapped_column(String(64), nullable=True)
    numbers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class TrunkPoolRow(Base):
    __tablename__ = "trunk_pools"
    __table_args__ = (
        UniqueConstraint("provider_name", "name", name="uq_trunk_pools_provider_name"),
    )

    trunk_pool_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    selection_policy: Mapped[str] = mapped_column(String(64), nullable=False, default="first_available")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class TrunkPoolMemberRow(Base):
    __tablename__ = "trunk_pool_members"
    __table_args__ = (
        UniqueConstraint("trunk_pool_id", "trunk_id", name="uq_trunk_pool_members_pool_trunk"),
    )

    trunk_pool_member_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trunk_pool_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trunk_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class TenantTrunkPoolRow(Base):
    __tablename__ = "tenant_trunk_pools"
    __table_args__ = (
        UniqueConstraint("tenant_id", "trunk_pool_id", name="uq_tenant_trunk_pools_tenant_pool"),
        CheckConstraint(
            "(max_channels IS NULL OR max_channels >= 1)",
            name="ck_tenant_trunk_pools_max_channels_min",
        ),
        CheckConstraint(
            "(reserved_channels IS NULL OR reserved_channels >= 0)",
            name="ck_tenant_trunk_pools_reserved_channels_min",
        ),
        CheckConstraint(
            "(max_channels IS NULL OR reserved_channels IS NULL OR reserved_channels <= max_channels)",
            name="ck_tenant_trunk_pools_reserved_le_max",
        ),
    )

    tenant_trunk_pool_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    trunk_pool_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reserved_channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class BotDestinationRow(Base):
    __tablename__ = "bot_destinations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_bot_destinations_tenant_name"),
        CheckConstraint(
            "protocol IN ('sip', 'http', 'webrtc', 'mock')",
            name="ck_bot_destinations_protocol",
        ),
        CheckConstraint(
            "(provisioned_channels IS NULL OR provisioned_channels >= 1)",
            name="ck_bot_destinations_provisioned_channels_min",
        ),
        CheckConstraint(
            "(reserved_channels IS NULL OR reserved_channels >= 0)",
            name="ck_bot_destinations_reserved_channels_min",
        ),
        CheckConstraint(
            "(botcheck_max_channels IS NULL OR botcheck_max_channels >= 1)",
            name="ck_bot_destinations_botcheck_max_channels_min",
        ),
        CheckConstraint(
            "(provisioned_channels IS NULL OR reserved_channels IS NULL "
            "OR reserved_channels <= provisioned_channels)",
            name="ck_bot_destinations_reserved_le_provisioned",
        ),
    )

    destination_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    protocol: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DestinationProtocol.MOCK.value
    )
    endpoint: Mapped[str | None] = mapped_column(String(512), nullable=True)
    caller_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trunk_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trunk_pool_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    headers: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    direct_http_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    webrtc_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    provisioned_channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reserved_channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    botcheck_max_channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capacity_scope: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class GraiEvalSuiteRow(Base):
    __tablename__ = "grai_eval_suites"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_grai_eval_suites_tenant_name"),
        Index("ix_grai_eval_suites_tenant_updated", "tenant_id", "updated_at"),
    )

    suite_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_yaml: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class GraiEvalPromptRow(Base):
    __tablename__ = "grai_eval_prompts"
    __table_args__ = (
        UniqueConstraint("suite_id", "order_index", name="uq_grai_eval_prompts_suite_order"),
        UniqueConstraint("suite_id", "label", name="uq_grai_eval_prompts_suite_label"),
    )

    prompt_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    suite_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class GraiEvalCaseRow(Base):
    __tablename__ = "grai_eval_cases"
    __table_args__ = (
        UniqueConstraint("suite_id", "order_index", name="uq_grai_eval_cases_suite_order"),
    )

    case_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    suite_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    vars_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    assert_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    tags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
    import_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


_GRAI_ASSERTION_TYPE_SQL = ", ".join(f"'{member.value}'" for member in GraiAssertionType)
_GRAI_EVAL_RUN_STATUS_SQL = ", ".join(f"'{member.value}'" for member in GraiEvalRunStatus)
_GRAI_EVAL_RUN_TERMINAL_OUTCOME_SQL = ", ".join(
    f"'{member.value}'" for member in GraiEvalRunTerminalOutcome
)


class GraiEvalRunRow(Base):
    __tablename__ = "grai_eval_runs"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_GRAI_EVAL_RUN_STATUS_SQL})",
            name="ck_grai_eval_runs_status",
        ),
        CheckConstraint(
            "terminal_outcome IS NULL OR "
            f"terminal_outcome IN ({_GRAI_EVAL_RUN_TERMINAL_OUTCOME_SQL})",
            name="ck_grai_eval_runs_terminal_outcome",
        ),
        Index("ix_grai_eval_runs_tenant_created", "tenant_id", "created_at"),
    )

    eval_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    suite_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    transport_profile_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    endpoint_at_start: Mapped[str] = mapped_column(String(512), nullable=False)
    headers_at_start: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    direct_http_config_at_start: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    trigger_source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    schedule_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    triggered_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=GraiEvalRunStatus.PENDING.value,
    )
    terminal_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    prompt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_pairs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dispatched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class GraiEvalRunDestinationRow(Base):
    __tablename__ = "grai_eval_run_destinations"
    __table_args__ = (
        UniqueConstraint("eval_run_id", "destination_index", name="uq_grai_eval_run_destinations_run_index"),
        Index("ix_grai_eval_run_destinations_tenant_run", "tenant_id", "eval_run_id"),
    )

    run_dest_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    eval_run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("grai_eval_runs.eval_run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    destination_index: Mapped[int] = mapped_column(Integer, nullable=False)
    transport_profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    protocol: Mapped[str] = mapped_column(String(32), nullable=False)
    endpoint_at_start: Mapped[str] = mapped_column(String(512), nullable=False)
    headers_at_start: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    direct_http_config_at_start: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class GraiEvalResultRow(Base):
    __tablename__ = "grai_eval_results"
    __table_args__ = (
        CheckConstraint(
            f"assertion_type IN ({_GRAI_ASSERTION_TYPE_SQL})",
            name="ck_grai_eval_results_assertion_type",
        ),
        UniqueConstraint(
            "eval_run_id",
            "prompt_id",
            "case_id",
            "destination_index",
            "assertion_index",
            name="uq_grai_eval_results_eval_prompt_case_assertion",
        ),
        Index("ix_grai_eval_results_run_assertion_passed", "eval_run_id", "assertion_type", "passed"),
        Index("ix_grai_eval_results_run_prompt", "eval_run_id", "prompt_id"),
        Index("ix_grai_eval_results_run_destination", "eval_run_id", "destination_index"),
    )

    eval_result_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    suite_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    eval_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    prompt_id: Mapped[str] = mapped_column(String(64), nullable=False)
    case_id: Mapped[str] = mapped_column(String(64), nullable=False)
    destination_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    assertion_index: Mapped[int] = mapped_column(Integer, nullable=False)
    assertion_type: Mapped[str] = mapped_column(String(64), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    raw_s3_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class ScenarioPackRow(Base):
    __tablename__ = "scenario_packs"

    pack_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    execution_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="parallel")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class ScenarioPackItemRow(Base):
    __tablename__ = "scenario_pack_items"
    __table_args__ = (
        UniqueConstraint("pack_id", "scenario_id", name="uq_pack_scenario"),
    )

    item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pack_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scenario_id: Mapped[str] = mapped_column(String(255), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)


class PackRunRow(Base):
    __tablename__ = "pack_runs"

    pack_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pack_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    destination_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    transport_profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    dial_target: Mapped[str | None] = mapped_column(String(512), nullable=True)
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PackRunState.PENDING.value
    )
    trigger_source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    schedule_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    triggered_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    gate_outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="error")
    total_scenarios: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dispatched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class PackRunItemRow(Base):
    __tablename__ = "pack_run_items"
    __table_args__ = (
        UniqueConstraint("pack_run_id", "scenario_id", name="uq_pack_run_item_scenario"),
    )

    pack_run_item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pack_run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    scenario_id: Mapped[str] = mapped_column(String(255), nullable=False)
    scenario_version_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditLogRow(Base):
    __tablename__ = "audit_log"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False, default="user")
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )


class TenantRow(Base):
    __tablename__ = "tenants"
    __table_args__ = (UniqueConstraint("slug", name="uq_tenants_slug"),)

    tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    feature_overrides: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    quota_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class PlatformSettingsRow(Base):
    __tablename__ = "platform_settings"

    singleton_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    feature_flags: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    quota_defaults: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class ProviderCatalogRow(Base):
    __tablename__ = "provider_catalog"

    provider_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    vendor: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    capability: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    runtime_scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    supports_tenant_credentials: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_platform_credentials: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cost_per_input_token_microcents: Mapped[int | None] = mapped_column(nullable=True)
    cost_per_output_token_microcents: Mapped[int | None] = mapped_column(nullable=True)
    cost_per_audio_second_microcents: Mapped[int | None] = mapped_column(nullable=True)
    cost_per_character_microcents: Mapped[int | None] = mapped_column(nullable=True)
    cost_per_request_microcents: Mapped[int | None] = mapped_column(nullable=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    user_created: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ProviderCredentialRow(Base):
    __tablename__ = "provider_credentials"
    __table_args__ = (
        UniqueConstraint("owner_scope", "tenant_id", "provider_id", name="uq_provider_credentials_owner_tenant_provider"),
    )

    credential_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_scope: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None, index=True)
    provider_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("provider_catalog.provider_id"),
        nullable=False,
        index=True,
    )
    credential_source: Mapped[str] = mapped_column(String(32), nullable=False)
    secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_secret_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class TenantProviderAssignmentRow(Base):
    __tablename__ = "tenant_provider_assignments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider_id", name="uq_tenant_provider_assignments_tenant_provider"),
        UniqueConstraint("provider_id", name="uq_tenant_provider_assignments_provider"),
    )

    assignment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("provider_catalog.provider_id"),
        nullable=False,
        index=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    effective_credential_source: Mapped[str] = mapped_column(String(32), nullable=False, default="env")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class ProviderQuotaPolicyRow(Base):
    __tablename__ = "provider_quota_policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider_id", "metric", name="uq_provider_quota_policies_tenant_provider_metric"),
    )

    quota_policy_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("provider_catalog.provider_id"),
        nullable=False,
        index=True,
    )
    metric: Mapped[str] = mapped_column(String(32), nullable=False)
    limit_per_day: Mapped[int] = mapped_column(nullable=False)
    soft_limit_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class ProviderUsageLedgerRow(Base):
    __tablename__ = "provider_usage_ledger"
    __table_args__ = (
        Index("ix_provider_usage_ledger_tenant_provider_recorded_at", "tenant_id", "provider_id", "recorded_at"),
        UniqueConstraint("usage_key", name="uq_provider_usage_ledger_usage_key"),
    )

    ledger_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    usage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("provider_catalog.provider_id"),
        nullable=False,
        index=True,
    )
    runtime_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    capability: Mapped[str] = mapped_column(String(32), nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    eval_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    input_tokens: Mapped[int] = mapped_column(nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(nullable=False, default=0)
    audio_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    characters: Mapped[int] = mapped_column(nullable=False, default=0)
    sip_minutes: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    calculated_cost_microcents: Mapped[int | None] = mapped_column(nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
        CheckConstraint(
            "role IN ('viewer', 'operator', 'editor', 'admin', 'system_admin')",
            name="ck_users_role",
        ),
    )

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="viewer")
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    totp_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sessions_invalidated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class RecoveryCodeRow(Base):
    __tablename__ = "recovery_codes"

    code_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )


class AuthSessionRow(Base):
    __tablename__ = "auth_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    refresh_token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    amr: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
