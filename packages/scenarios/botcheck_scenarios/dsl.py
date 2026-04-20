"""
BotCheck Scenario DSL - Pydantic models for scenario YAML files.

A scenario describes a complete test conversation between the BotCheck
harness agent (the synthetic caller) and the voicebot under test.
"""

from __future__ import annotations

import glob
import hashlib
import os
import re

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from .blocks import (
    BotListenBlock,
    HangupBlock,
    HarnessPromptBlock,
    ScenarioBlock,
    TimeRouteBlock,
    WaitBlock,
    load_block,
    normalize_legacy_turn_to_block,
)
from .persona import PersonaConfig, PersonaMood, ResponseStyle
from .scoring import DimensionRubric, ScenarioScoring, ScoringDimension
from .speech import parse_tts_voice
from .turns import (
    AdversarialTechnique,
    BotConfig,
    BotProtocol,
    BranchCase,
    BranchConfig,
    BranchMode,
    ScenarioConfig,
    ScenarioType,
    Turn,
    TurnConfig,
    TurnExpectation,
)


class ScenarioDefinition(BaseModel):
    """
    Root model for a BotCheck scenario YAML file.

    Example minimal scenario:

        version: "1.0"
        id: golden-path-billing
        name: "Golden Path - Billing Query"
        type: golden_path
        bot:
          endpoint: "sip:${BOT_SIP_USER}@${SIP_PROVIDER}"
          protocol: sip
        turns:
          - id: t1
            text: "Hi, I need to check my account balance."
            wait_for_response: true
            expect:
              intent_recognized: true
    """

    version: str = "1.0"
    id: str
    name: str
    namespace: str | None = None
    type: ScenarioType
    description: str = ""
    http_request_context: dict[str, object] = Field(default_factory=dict)

    bot: BotConfig
    persona: PersonaConfig = Field(default_factory=PersonaConfig)
    config: ScenarioConfig = Field(default_factory=ScenarioConfig)
    turns: list[ScenarioBlock]
    scoring: ScenarioScoring = Field(default_factory=ScenarioScoring)
    tags: list[str] = Field(default_factory=list)

    @field_validator("namespace", mode="before")
    @classmethod
    def normalize_namespace(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        normalized = value.strip().strip("/")
        return normalized or None

    @field_validator("http_request_context", mode="before")
    @classmethod
    def normalize_http_request_context(cls, value: object) -> dict[str, object]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("http_request_context must be an object")
        return dict(value)

    @field_validator("turns", mode="before")
    @classmethod
    def normalize_turns(cls, value: object) -> object:
        if not isinstance(value, list):
            return value

        normalized: list[ScenarioBlock] = []
        for item in value:
            if isinstance(
                item,
                (HarnessPromptBlock, BotListenBlock, HangupBlock, WaitBlock, TimeRouteBlock),
            ):
                normalized.append(item)
                continue
            if isinstance(item, Turn):
                normalized.append(normalize_legacy_turn_to_block(item.model_dump()))
                continue
            if isinstance(item, dict):
                normalized.append(load_block(dict(item)))
                continue
            raise ValueError(
                f"Unexpected turn item type {type(item).__name__!r} — "
                "each turn must be a dict, Turn, or ScenarioBlock"
            )
        return normalized

    @model_validator(mode="after")
    def validate_turns(self) -> ScenarioDefinition:
        if not self.turns:
            raise ValueError("Scenario must have at least one turn")

        # At least one playable (non-hangup) block is required — a scenario that
        # consists solely of HangupBlock markers is not meaningful.
        playable = [t for t in self.turns if not isinstance(t, HangupBlock)]
        if not playable:
            raise ValueError("Scenario must have at least one playable (non-hangup) turn")

        turn_ids = [turn.id for turn in self.turns]
        if len(turn_ids) != len(set(turn_ids)):
            raise ValueError("Scenario turn ids must be unique")

        known_ids = set(turn_ids)
        for turn in self.turns:
            if isinstance(turn, TimeRouteBlock):
                if turn.default not in known_ids:
                    raise ValueError(
                        f"Turn '{turn.id}': time_route default target "
                        f"'{turn.default}' does not exist in scenario turns"
                    )
                for window in turn.windows:
                    if window.next not in known_ids:
                        raise ValueError(
                            f"Turn '{turn.id}': time_route window '{window.label}' target "
                            f"'{window.next}' does not exist in scenario turns"
                        )
                continue
            next_turn = getattr(turn, "next", None)
            branching = getattr(turn, "branching", None)
            if next_turn and next_turn not in known_ids:
                raise ValueError(
                    f"Turn '{turn.id}': next target '{next_turn}' does not exist in scenario turns"
                )
            if branching is None:
                continue
            if branching.default not in known_ids:
                raise ValueError(
                    f"Turn '{turn.id}': branching.default target "
                    f"'{branching.default}' does not exist in scenario turns"
                )
            for case in branching.cases:
                if case.next not in known_ids:
                    raise ValueError(
                        f"Turn '{turn.id}': branching case '{case.condition}' target "
                        f"'{case.next}' does not exist in scenario turns"
                    )

        return self

    @property
    def adversarial_turns(self) -> list[HarnessPromptBlock | BotListenBlock]:
        return [turn for turn in self.turns if turn.adversarial]

    @property
    def has_gate_dimensions(self) -> bool:
        return any(dimension.gate for dimension in self.scoring.rubric)

    @staticmethod
    def _split_tts_voice(voice: str) -> tuple[str, str]:
        """
        Split "provider:voice" into components.

        If the provider prefix is missing, default to openai for backward
        compatibility with legacy scenario configs.
        """
        parsed = parse_tts_voice(voice)
        return (parsed.provider, parsed.voice)

    @staticmethod
    def _normalise_turn_text(text: str) -> str:
        return " ".join(text.split())

    def turn_content_hash(
        self,
        turn: HarnessPromptBlock,
        *,
        pcm_format_version: str = "v1",
    ) -> str:
        """
        Stable content hash for a cacheable harness turn.

        Hash input includes all synthesis-relevant fields so cache invalidation
        follows real audio changes, not unrelated scenario edits.
        """
        if not isinstance(turn, HarnessPromptBlock):
            raise ValueError("turn_content_hash only supports harness-speaker turns")
        if not turn.content.text:
            raise ValueError("turn_content_hash requires a harness turn with text")

        parsed_voice = parse_tts_voice(self.config.tts_voice)
        payload = "|".join(
            [
                self._normalise_turn_text(turn.content.text),
                parsed_voice.provider,
                parsed_voice.voice,
                self.persona.mood.value,
                self.persona.response_style.value,
                pcm_format_version,
            ]
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def turn_cache_key(
        self,
        turn: HarnessPromptBlock,
        tenant_id: str,
        *,
        pcm_format_version: str = "v1",
    ) -> str:
        """
        Build tenant-scoped cache key for a turn's synthesized WAV.
        """
        if not tenant_id.strip():
            raise ValueError("tenant_id is required")
        content_hash = self.turn_content_hash(
            turn,
            pcm_format_version=pcm_format_version,
        )
        return f"{tenant_id}/tts-cache/{turn.id}/{content_hash}.wav"

    def json_schema(self) -> dict:
        """Return the JSON Schema for this model (useful for editor tooling)."""
        return self.model_json_schema()


_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def _substitute_env(content: str) -> str:
    """Replace ${VAR} placeholders with environment variable values."""

    def replace(match: re.Match) -> str:
        var = match.group(1)
        value = os.environ.get(var)
        if value is None:
            raise ValueError(
                f"Scenario references environment variable '${{{var}}}' which is not set."
            )
        return value

    return _ENV_VAR_RE.sub(replace, content)


def load_scenario(path: str) -> ScenarioDefinition:
    """Load, env-substitute, and validate a scenario from a YAML file."""
    with open(path) as file_obj:
        content = file_obj.read()
    content = _substitute_env(content)
    raw = yaml.safe_load(content)
    return ScenarioDefinition.model_validate(raw)


def load_scenarios_dir(directory: str) -> list[ScenarioDefinition]:
    """Load all .yaml/.yml scenarios from a directory tree."""
    paths = sorted(
        glob.glob(f"{directory}/**/*.yaml", recursive=True)
        + glob.glob(f"{directory}/**/*.yml", recursive=True)
    )
    return [load_scenario(path) for path in paths]


__all__ = [
    "ScenarioDefinition",
    "ScenarioType",
    "Turn",
    "TurnExpectation",
    "TurnConfig",
    "BranchCase",
    "BranchConfig",
    "BranchMode",
    "BotConfig",
    "BotProtocol",
    "PersonaConfig",
    "PersonaMood",
    "ResponseStyle",
    "ScenarioConfig",
    "ScenarioScoring",
    "DimensionRubric",
    "ScoringDimension",
    "AdversarialTechnique",
    "load_scenario",
    "load_scenarios_dir",
]
