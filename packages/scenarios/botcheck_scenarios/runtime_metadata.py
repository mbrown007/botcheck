from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _room_metadata_text(value: str | None, *, max_len: int = 1200) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:max_len]


class AIRunContextSnapshot(BaseModel):
    dataset_input: str
    expected_output: str
    persona_id: str
    persona_name: str | None = None
    scenario_brief: str | None = None
    scenario_objective: str | None = None
    opening_strategy: str = "wait_for_bot_greeting"

    def room_metadata_items(self, *, max_len: int = 1200) -> dict[str, str]:
        out: dict[str, str] = {}
        for key, value in (
            ("dataset_input", self.dataset_input),
            ("expected_output", self.expected_output),
            ("persona_id", self.persona_id),
            ("persona_name", self.persona_name),
            ("scenario_brief", self.scenario_brief),
            ("scenario_objective", self.scenario_objective),
            ("opening_strategy", self.opening_strategy),
        ):
            text = _room_metadata_text(value, max_len=max_len)
            if text is not None:
                out[f"ai_{key}"] = text
        return out


class AIRunDispatchContext(BaseModel):
    """Reader-side projection of the AI-run fields stamped into room metadata.

    ``extra="ignore"`` is intentional: this model is always validated against a
    superset dict (``RunRoomMetadata.model_dump()``), so unknown keys must be
    silently dropped rather than rejected.  Patch ``botcheck_api.auth.security``
    directly when monkeypatching — do not patch through this module.
    """

    model_config = ConfigDict(extra="ignore")

    ai_dataset_input: str | None = None
    ai_expected_output: str | None = None
    ai_persona_id: str | None = None
    ai_persona_name: str | None = None
    ai_scenario_brief: str | None = None
    ai_scenario_objective: str | None = None
    ai_opening_strategy: str | None = None

    @field_validator(
        "ai_dataset_input",
        "ai_expected_output",
        "ai_persona_id",
        "ai_persona_name",
        "ai_scenario_brief",
        "ai_scenario_objective",
        "ai_opening_strategy",
        mode="before",
    )
    @classmethod
    def _normalize_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def objective_hint(self) -> str:
        """Return the best available objective description for the AI caller prompt.

        Fallback order: scenario_objective → scenario_brief → expected_output.
        Note: using ``ai_expected_output`` as a last resort can bias generated
        utterances toward rubric-satisfying language; omit it in adversarial
        scenarios by always providing ``ai_scenario_objective`` or
        ``ai_scenario_brief``.
        """
        return (
            self.ai_scenario_objective
            or self.ai_scenario_brief
            or self.ai_expected_output
            or ""
        )

    def effective_opening_strategy(self) -> str:
        """Return the resolved opening strategy, defaulting to 'wait_for_bot_greeting'."""
        return self.ai_opening_strategy or "wait_for_bot_greeting"


class RunExecutionMetadata(BaseModel):
    """Reader-side projection of run-level routing fields from room metadata.

    ``extra="ignore"`` is intentional: this model is validated against the full
    ``RunRoomMetadata`` payload, so unrelated keys are silently dropped.
    Helper methods lowercase their return values; the stored field values are
    stripped but NOT lowercased, so always call the helpers rather than
    accessing fields directly when case-sensitive comparisons are needed.
    """

    model_config = ConfigDict(extra="ignore")

    scenario_kind: str | None = None
    ai_opening_strategy: str | None = None
    run_type: str | None = None
    transport: str | None = None
    bot_protocol: str | None = None

    @field_validator(
        "scenario_kind",
        "ai_opening_strategy",
        "run_type",
        "transport",
        "bot_protocol",
        mode="before",
    )
    @classmethod
    def _normalize_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def normalized_scenario_kind(self) -> str:
        return (self.scenario_kind or "").lower()

    def normalized_run_type(self) -> str:
        return (self.run_type or "").lower()

    def effective_opening_strategy(self) -> str:
        """Return the resolved opening strategy, defaulting to 'wait_for_bot_greeting'."""
        return (self.ai_opening_strategy or "wait_for_bot_greeting").lower()

    def transport_protocol(self) -> str:
        """Return the active transport protocol, lower-cased.

        Returns an empty string when neither ``transport`` nor ``bot_protocol``
        is set.  Callers should treat ``""`` as the default LiveKit/SIP path
        (i.e. the absence of a non-SIP override), not as an error.
        """
        return (self.transport or self.bot_protocol or "").lower()


class RunRoomMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    scenario_kind: str = "graph"
    tenant_id: str | None = None
    trigger_source: str = "manual"
    run_type: str | None = None
    bot_protocol: str | None = None
    transport: str | None = None
    effective_tts_voice: str | None = None
    effective_stt_provider: str | None = None
    effective_stt_model: str | None = None
    schedule_id: str | None = None
    playground_mode: str | None = None
    ai_scenario_id: str | None = None
    destination_id: str | None = None
    transport_profile_id: str | None = None
    trunk_pool_id: str | None = None
    dial_target: str | None = None
    ai_dataset_input: str | None = None
    ai_expected_output: str | None = None
    ai_persona_id: str | None = None
    ai_persona_name: str | None = None
    ai_scenario_brief: str | None = None
    ai_scenario_objective: str | None = None
    ai_opening_strategy: str | None = None
    traceparent: str | None = None
    tracestate: str | None = None
