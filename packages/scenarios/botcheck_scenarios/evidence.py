"""
BotCheck Evidence Format — output models produced by the Judge Service.

A RunReport is the authoritative record of what happened in a test run:
  - the conversation transcript (verbatim turns)
  - scored dimensions with pass/fail/warn status
  - findings with cited turn numbers and quoted text
  - deterministic checks
  - gate result for CI integration
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from .dsl import ScoringDimension


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class RunStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    ERROR = "error"  # infrastructure / technical error, not a scoring failure


class GateResult(str, Enum):
    PASSED = "passed"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"  # scenario opted out of gating


class MetricType(str, Enum):
    SCORE = "score"
    FLAG = "flag"


class ConversationTurn(BaseModel):
    """A single exchange recorded verbatim during the test run."""

    turn_id: str
    """Matches the Turn.id from the scenario definition."""

    turn_number: int
    """1-based sequence number within the conversation."""

    speaker: str
    """'harness' or 'bot'."""

    text: str
    """Full ASR transcript of this turn."""

    audio_start_ms: int
    """Millisecond offset from call start when this turn began."""

    audio_end_ms: int
    """Millisecond offset from call start when this turn ended."""

    adversarial: bool = False
    technique: str | None = None


class Finding(BaseModel):
    """
    A single scored observation with verbatim evidence.

    The combination of quoted_text + turn_number + speaker makes every
    finding independently auditable without replaying the audio.
    """

    dimension: ScoringDimension
    turn_id: str
    turn_number: int
    visit: int | None = None
    """Optional 1-based visit index for repeated turn IDs in branching paths."""
    speaker: str

    quoted_text: str
    """The exact text from the transcript that this finding is based on."""

    finding: str
    """Human-readable description of what was observed."""

    severity: Severity

    positive: bool = False
    """
    True = this is a positive finding (e.g. correct refusal, correct routing).
    False = this is a negative finding (e.g. jailbreak success, wrong route).
    """


class DimensionScore(BaseModel):
    """Score and status for one scoring dimension."""

    metric_type: MetricType = MetricType.SCORE
    """`score` = continuous 0..1 value, `flag` = boolean pass/fail."""

    score: float | None = Field(default=None, ge=0.0, le=1.0)
    """Normalised score for `score` metrics. `flag` metrics use 1.0/0.0 compatibility."""

    passed: bool | None = None
    """Boolean result for `flag` metrics; null for `score` metrics."""

    status: RunStatus
    threshold: float
    gate: bool

    findings: list[Finding] = Field(default_factory=list)
    """All findings (positive and negative) that contributed to this score."""

    reasoning: str = ""
    """LLM judge's chain-of-thought reasoning for this dimension score."""


class DeterministicChecks(BaseModel):
    """
    Hard pass/fail checks that don't require LLM scoring.
    These are computed before the LLM judge and can short-circuit gating.
    """

    call_completed_in_budget: bool | None = None
    no_infinite_loop: bool | None = None

    transfer_target_correct: bool | None = None
    transfer_target_observed: str | None = None
    """Actual transfer target the bot routed to (extracted from SIP REFER or bot utterance)."""

    pii_not_requested: bool | None = None
    forbidden_phrase_not_uttered: bool | None = None
    forbidden_phrases_found: list[str] = Field(default_factory=list)
    not_role_switched: bool | None = None
    role_switch_turns: list[str] = Field(default_factory=list)

    timeout_turns: list[str] = Field(default_factory=list)
    """Turn IDs where the bot did not respond within turn_timeout_s."""

    interruptions_count: int | None = None
    long_pause_count: int | None = None
    p95_response_gap_ms: int | None = None
    """p95 Time to First Word (TTFW): p95 of harness→bot gap_ms across all turns."""
    interruption_recovery_pct: float | None = None
    turn_taking_efficiency_pct: float | None = None
    """% of bot responses where TTFW was within the pause_threshold_ms budget."""


class RunReport(BaseModel):
    """
    The complete output of a BotCheck test run.
    Written by the Judge Service; stored as an encrypted artifact.
    """

    # Identity
    run_id: str
    scenario_id: str
    scenario_version_hash: str
    """SHA-256 of the scenario YAML content at time of execution."""

    bot_endpoint: str
    tenant_id: str

    # Timing
    started_at: datetime
    completed_at: datetime
    duration_ms: int

    # Verdict
    overall_status: RunStatus
    gate_result: GateResult

    # Scores — keyed by ScoringDimension value string for JSON serialisation
    scores: dict[str, DimensionScore] = Field(default_factory=dict)

    # Deterministic checks (run before LLM scoring)
    deterministic: DeterministicChecks = Field(default_factory=DeterministicChecks)

    # Full conversation
    conversation: list[ConversationTurn] = Field(default_factory=list)

    # All findings across all dimensions (convenience for UI)
    all_findings: list[Finding] = Field(default_factory=list)

    # Provenance
    judge_model: str
    """Model ID used for semantic scoring (e.g. 'claude-sonnet-4-6')."""

    judge_version: str
    """Version of the Judge Service that produced this report."""

    # ---------------------------------------------------------------------------
    # Computed helpers
    # ---------------------------------------------------------------------------

    @property
    def failed_gate_dimensions(self) -> list[str]:
        return [
            dim
            for dim, score in self.scores.items()
            if score.gate and score.status == RunStatus.FAIL
        ]

    @property
    def worst_finding(self) -> Finding | None:
        """The highest-severity negative finding across all dimensions."""
        negative = [f for f in self.all_findings if not f.positive]
        if not negative:
            return None
        order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
            Severity.INFO: 4,
        }
        return min(negative, key=lambda f: order.get(f.severity, 99))

    @property
    def summary_line(self) -> str:
        """One-line summary suitable for CI output / Slack notification."""
        fail_count = sum(1 for s in self.scores.values() if s.status == RunStatus.FAIL)
        warn_count = sum(1 for s in self.scores.values() if s.status == RunStatus.WARN)
        pass_count = sum(1 for s in self.scores.values() if s.status == RunStatus.PASS)
        gate = "BLOCKED" if self.gate_result == GateResult.BLOCKED else "PASSED"
        return (
            f"Run {self.run_id} | {self.scenario_id} | "
            f"Gate: {gate} | "
            f"✓{pass_count} ⚠{warn_count} ✗{fail_count}"
        )
