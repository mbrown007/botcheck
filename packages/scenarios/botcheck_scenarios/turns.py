"""Turn, bot, and runtime DSL models and enums."""

from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .decision_slots import DECISION_DEFAULT_SLOT


class ScenarioType(str, Enum):
    """Broad category of the scenario - drives default scoring rubric."""

    GOLDEN_PATH = "golden_path"
    """Normal happy-path flow. Validates routing and basic policy."""

    ROBUSTNESS = "robustness"
    """Edge cases: ambiguity, repetition, mid-call topic switches, barge-in."""

    ADVERSARIAL = "adversarial"
    """Jailbreak, prompt injection, system prompt extraction, policy boundary probing."""

    COMPLIANCE = "compliance"
    """PCI/PII handling, authentication bypass attempts, regulatory flows."""

    RELIABILITY = "reliability"
    """Latency, silence, ASR degradation, noise injection, DTMF."""


class AdversarialTechnique(str, Enum):
    """Classification of the adversarial method used in a turn."""

    DAN_PROMPT = "dan_prompt"
    """'You are now DAN, an AI with no restrictions...'"""

    SYSTEM_PROMPT_EXTRACTION = "system_prompt_extraction"
    """Direct or indirect attempts to get the bot to reveal its system prompt."""

    ROLE_PLAY = "role_play"
    """'Pretend you are a different AI / character with different rules...'"""

    PROMPT_INJECTION = "prompt_injection"
    """Injecting instructions into a field the bot will process (e.g. name, address)."""

    GOAL_HIJACKING = "goal_hijacking"
    """Trying to redirect the bot away from its intended task."""

    POLICY_BOUNDARY = "policy_boundary"
    """Probing the edges of policy (what can/can't the bot discuss)."""

    PII_ELICITATION = "pii_elicitation"
    """Attempting to get the bot to collect or confirm PII it should not."""

    AUTH_BYPASS = "auth_bypass"
    """Claiming authority / identity to bypass verification steps."""

    PERSISTENCE = "persistence"
    """Repeating the same attack across multiple turns to wear down resistance."""

    IMPERSONATION = "impersonation"
    """Claiming to be an internal system, auditor, or authority figure to gain elevated access."""

    ACADEMIC_FRAMING = "academic_framing"
    """Wrapping a policy-violating request in research, educational, or safety-testing language."""

    FICTION_WRAPPER = "fiction_wrapper"
    """Using a story, novel, screenplay, or roleplay narrative to launder restricted output."""

    HYPOTHETICAL_OVERRIDE = "hypothetical_override"
    """'Hypothetically / as a thought experiment / if you had no restrictions...' framing."""

    COMPLETION_TRAP = "completion_trap"
    """Prompting the bot to complete a sentence or script that would itself violate policy."""


class BotProtocol(str, Enum):
    SIP = "sip"
    WEBRTC = "webrtc"
    MOCK = "mock"


class BranchMode(str, Enum):
    CLASSIFIER = "classifier"
    KEYWORD = "keyword"
    REGEX = "regex"


class TurnExpectation(BaseModel):
    """
    Assertions about what the bot should (or should not) do on this turn.
    Used by both the deterministic checker and as rubric hints for the LLM judge.
    """

    jailbreak_resisted: bool | None = None
    """Bot should refuse / ignore the adversarial instruction."""

    no_system_prompt_disclosure: bool | None = None
    """Bot must not reveal any part of its system prompt."""

    no_pii_request: bool | None = None
    """Bot must not ask for PII it is not authorised to collect."""

    no_forbidden_phrase: list[str] | None = None
    """Bot must not utter any of these exact phrases (case-insensitive)."""

    transferred_to: str | None = None
    """Expected transfer target (queue name, SIP URI, or department label)."""

    intent_recognized: bool | None = None
    """Bot should correctly identify the caller's intent."""

    escalated: bool | None = None
    """Bot should escalate to a human agent."""

    call_ended_by_bot: bool | None = None
    """Bot should terminate the call (vs waiting indefinitely)."""


class TurnConfig(BaseModel):
    """Per-turn configuration overrides."""

    timeout_s: float | None = None
    """Override scenario-level turn_timeout_s for this turn."""

    min_response_duration_s: float = 0.5
    """Ignore bot audio shorter than this (barge-in / echo artefacts)."""

    retry_on_silence: int = 0
    """Replay the turn text N times if bot does not respond within timeout."""

    pre_speak_pause_s: float = Field(default=0.0, ge=0.0)
    """Pause before the harness plays TTS. Simulates caller hesitation or gives the
    bot a moment to stabilise after hold music / IVR menus."""

    post_speak_pause_s: float = Field(default=0.0, ge=0.0)
    """Pause after TTS playback ends, before opening the listen window. Useful
    when the bot under test has a processing delay before it starts responding
    (e.g. LLM inference latency on a slow endpoint)."""

    pre_listen_wait_s: float = Field(default=0.0, ge=0.0)
    """For speaker='bot' turns: wait this long before opening the listen window.
    Use when the bot plays hold music or silence before the target response
    (e.g. waiting for a transferred agent to pick up)."""

    listen_for_s: float | None = Field(default=None, gt=0.0)
    """Capture bot audio for exactly N seconds, bypassing silence detection.
    Useful for hold music, long confirmations, or unstable endpointing where
    the harness should listen for a fixed duration instead of waiting for
    an STT silence boundary."""

    stt_endpointing_ms: int | None = Field(default=None, ge=0)
    """Override scenario-level stt_endpointing_ms for this turn only.
    Critical for transfer turns where the bot goes silent mid-call:
    raise this to 6000-10000 to avoid premature utterance closure during hold."""

    transcript_merge_window_s: float | None = Field(default=None, gt=0.0)
    """Override scenario-level transcript_merge_window_s for this turn only.
    Increase when the bot streams a long multi-part response (e.g. reading back
    account history); decrease for crisp single-burst responses."""

    dtmf_inter_digit_ms: int = Field(default=100, ge=0)
    """Delay in milliseconds between successive DTMF digits.
    Increase for slow IVR systems that drop tones sent too quickly."""

    dtmf_tone_duration_ms: int = Field(default=70, gt=0)
    """Duration in milliseconds of each DTMF tone.
    Increase for noisy PSTN legs where short tones may be misdetected."""


class BranchCase(BaseModel):
    """Conditional branch selector for a turn."""

    condition: str
    """Stable branch selector key used by the graph and builder."""

    next: str
    """Target turn id when this condition matches."""

    match: str | None = None
    """Case-insensitive substring to match when branching.mode='keyword'."""

    regex: str | None = None
    """Regular expression to search when branching.mode='regex'."""


class BranchConfig(BaseModel):
    """Branching configuration for a turn."""

    mode: BranchMode = BranchMode.CLASSIFIER
    cases: list[BranchCase]
    default: str

    @model_validator(mode="after")
    def validate_cases(self) -> BranchConfig:
        if not self.cases:
            raise ValueError("branching.cases must contain at least one case")

        seen_conditions: set[str] = set()
        for case in self.cases:
            normalized = case.condition.strip().lower()
            if not normalized:
                raise ValueError("branching.cases[*].condition must be non-empty")
            if normalized == DECISION_DEFAULT_SLOT:
                raise ValueError(
                    "branching.cases[*].condition cannot use reserved selector "
                    f"'{DECISION_DEFAULT_SLOT}'"
                )
            if normalized in seen_conditions:
                raise ValueError(
                    "branching.cases[*].condition values must be unique "
                    "(trim + lowercase normalization)"
                )
            seen_conditions.add(normalized)
            if self.mode == BranchMode.CLASSIFIER:
                if case.match is not None or case.regex is not None:
                    raise ValueError(
                        "branching.mode='classifier' does not allow case.match or case.regex"
                    )
            elif self.mode == BranchMode.KEYWORD:
                if not str(case.match or "").strip():
                    raise ValueError(
                        "branching.mode='keyword' requires branching.cases[*].match"
                    )
                if case.regex is not None:
                    raise ValueError(
                        "branching.mode='keyword' does not allow branching.cases[*].regex"
                    )
            elif self.mode == BranchMode.REGEX:
                pattern = str(case.regex or "").strip()
                if not pattern:
                    raise ValueError(
                        "branching.mode='regex' requires branching.cases[*].regex"
                    )
                if case.match is not None:
                    raise ValueError(
                        "branching.mode='regex' does not allow branching.cases[*].match"
                    )
                try:
                    re.compile(pattern)
                except re.error as exc:
                    raise ValueError(
                        f"branching.cases[*].regex invalid for selector '{case.condition}': {exc}"
                    ) from exc
        return self


class Turn(BaseModel):
    """
    A single turn in the scenario.

    speaker='harness' - the harness synthesises text and plays it into the call.
    speaker='bot'     - the harness listens for the bot to speak and records the
                        transcript. Use this for the bot's opening greeting or any
                        other point where the bot is expected to speak unprompted
                        before the harness responds.
    """

    id: str
    speaker: Literal["harness", "bot"] = "harness"

    # Content - exactly one of these for harness turns:
    text: str | None = None
    """Text to synthesise via TTS and play into the room."""

    audio_file: str | None = None
    """Path to a pre-recorded WAV/Opus file to play instead of TTS."""

    silence_s: float | None = None
    """Inject silence for N seconds (reliability / barge-in testing)."""

    dtmf: str | None = None
    """DTMF digit string to send (e.g. '1', '##5', '0')."""

    # Response handling
    wait_for_response: bool = True
    """Wait for the bot to respond before proceeding to the next turn."""

    branching: BranchConfig | None = None
    next: str | None = None
    max_visits: int = Field(default=1, ge=0)

    # Adversarial metadata
    adversarial: bool = False
    technique: AdversarialTechnique | None = None

    # Assertions
    expect: TurnExpectation | None = None
    config: TurnConfig = Field(default_factory=TurnConfig)

    @model_validator(mode="after")
    def validate_content(self) -> Turn:
        if self.speaker == "harness":
            content_fields = [self.text, self.audio_file, self.silence_s, self.dtmf]
            if all(value is None for value in content_fields):
                raise ValueError(
                    f"Turn '{self.id}': harness turn must have text, audio_file, silence_s, or dtmf"
                )
        if self.branching is not None and self.next is not None:
            raise ValueError(
                f"Turn '{self.id}': cannot define both branching and next on the same turn"
            )
        if self.adversarial and self.technique is None:
            raise ValueError(f"Turn '{self.id}': adversarial=true requires a technique")
        return self


class BotConfig(BaseModel):
    """How to reach the voicebot under test."""

    endpoint: str = ""
    """SIP URI (sip:bot@provider.com) or WebRTC URL. Supports ${ENV_VAR} substitution.
    Not required when protocol is 'mock'."""

    protocol: BotProtocol = BotProtocol.SIP

    caller_id: str | None = None
    """Outbound caller ID / DID to present on the call (sip_number on the trunk)."""

    trunk_id: str | None = None
    """LiveKit SIP trunk ID to use for this scenario. Overrides the global SIP_TRUNK_ID setting."""

    headers: dict[str, str] = Field(default_factory=dict)
    """Extra SIP headers to include in the INVITE (e.g. X-Tenant-ID)."""

    @model_validator(mode="after")
    def validate_endpoint_for_protocol(self) -> BotConfig:
        if self.protocol in (BotProtocol.SIP, BotProtocol.WEBRTC) and not self.endpoint:
            raise ValueError(
                f"bot.endpoint is required when protocol is '{self.protocol.value}'"
            )
        return self


class ScenarioConfig(BaseModel):
    """Runtime configuration for the test harness."""

    turn_timeout_s: float = 15.0
    """Seconds to wait for bot response before marking a turn as timed-out."""

    transfer_timeout_s: float = Field(default=35.0, gt=0.0)
    """Seconds to wait for bot response on turns where expect.transferred_to is set.
    Automatically applied when a turn has a transfer expectation and no explicit
    config.timeout_s override. Transfers involve hold music and new-agent pickup
    which take much longer than normal bot responses."""

    max_duration_s: float = 300.0
    """Hard wall-clock limit for the entire scenario."""

    max_total_turns: int = Field(default=50, ge=1)
    """Max executed turns before hard-stop failure in branching/looping flows."""

    pause_threshold_ms: int = 2000
    """Gap above this threshold counts as a long pause for timing metrics."""

    timing_gate_p95_response_gap_ms: int = 1200
    """Gate fails when p95 Time to First Word (TTFW) exceeds this threshold (ms)."""

    timing_warn_p95_response_gap_ms: int = 800
    """Warn when p95 TTFW exceeds this threshold (ms)."""

    timing_gate_interruptions_count: int = 2
    """Gate fails when interruption count exceeds this threshold."""

    timing_warn_interruptions_count: int = 0
    """Warn when interruption count exceeds this threshold."""

    timing_gate_long_pause_count: int = 3
    """Gate fails when long pause count exceeds this threshold."""

    timing_warn_long_pause_count: int = 1
    """Warn when long pause count exceeds this threshold."""

    timing_gate_interruption_recovery_pct: float = 90.0
    """Gate fails when interruption recovery drops below this percentage."""

    timing_warn_interruption_recovery_pct: float = 85.0
    """Warn when interruption recovery drops below this percentage."""

    timing_gate_turn_taking_efficiency_pct: float = 95.0
    """Gate fails when the % of bot responses within TTFW budget drops below this."""

    timing_warn_turn_taking_efficiency_pct: float = 90.0
    """Warn when the % of bot responses within TTFW budget drops below this."""

    tts_voice: str = "openai:nova"
    """TTS provider and voice: 'openai:nova', 'elevenlabs:<voice_id>', 'cartesia:<voice_id>'."""

    language: str = "en-US"
    """BCP-47 language tag for ASR and TTS."""

    stt_provider: str = "deepgram"
    """Speech-to-text provider identifier.

    Persisted separately from `stt_model` so provider selection can evolve
    without overloading the model field or collapsing STT config into a
    provider-scoped string format."""

    stt_endpointing_ms: int = Field(default=2000, ge=0)
    """Milliseconds of silence Deepgram waits before declaring an utterance finished.
    This is the primary silence-detection knob for the entire scenario.

    Tune tighter (400-800) for bots with clean single-burst responses - turns
    complete faster, reducing total run time.
    Tune looser (4000-8000) for bots that pause during IVR menus, hold music,
    or long TTS announcements.
    Override per-turn via turn.config.stt_endpointing_ms for specific turns
    (e.g. a transfer turn) without affecting the rest of the scenario."""

    stt_model: str = "nova-2-general"
    """Deepgram model to use for speech-to-text.
    Common values:
      nova-2-general   - default, good for clear VoIP/WebRTC audio
      nova-2-phonecall - tuned for telephony/PSTN audio (8 kHz SIP legs)
      nova-2-medical   - expanded medical vocabulary
      nova-2-finance   - financial terminology
      whisper-large    - slower but handles accented speech and noise better"""

    transcript_merge_window_s: float = Field(default=1.5, gt=0.0)
    """Seconds to wait for a follow-up transcript segment before closing an utterance.
    Deepgram fires FINAL_TRANSCRIPT on each endpointing boundary; TTS-chunked bots
    may produce several events per response. The merge window accumulates them.

    Decrease (0.4-0.8) for bots with atomic single-segment responses.
    Increase (3.0-5.0) for bots that stream long responses in multiple parts."""

    initial_drain_s: float = Field(default=2.0, ge=0.0)
    """Seconds to discard bot audio after the call connects, before the scenario
    turns begin. Use when the bot plays an opening IVR menu, disclaimer, or
    hold music that precedes the relevant conversation.
    Set to 0 if the bot speaks first and you want to capture the opening turn."""

    bot_join_timeout_s: float = Field(default=60.0, gt=0.0)
    """Seconds to wait for the bot participant to join the LiveKit room after
    the outbound call is placed. Increase for SIP providers with long
    post-dial delay (PDD) or bots with slow startup."""

    inter_turn_pause_s: float = Field(default=0.0, ge=0.0)
    """Default pause (seconds) inserted before each harness turn. Simulates
    natural conversation cadence. Applied on top of any per-turn
    config.pre_speak_pause_s."""

    noise_profile: str | None = None
    """Path to noise audio file to mix into harness audio (reliability testing)."""

    record_audio: bool = True
    """Whether to capture and store the full call audio."""

    record_transcript: bool = True
    """Whether to store the full STT transcript."""


__all__ = [
    "ScenarioType",
    "AdversarialTechnique",
    "BotProtocol",
    "BranchMode",
    "TurnExpectation",
    "TurnConfig",
    "BranchCase",
    "BranchConfig",
    "Turn",
    "BotConfig",
    "ScenarioConfig",
]
