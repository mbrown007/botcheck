"""Normalized scenario block models and legacy turn normalization."""

from __future__ import annotations

import re
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, TypeAdapter, model_validator

from .turns import AdversarialTechnique, BranchConfig, Turn, TurnConfig, TurnExpectation


class PromptContent(BaseModel):
    """Prompt content for a harness block."""

    text: str | None = None
    audio_file: str | None = None
    silence_s: float | None = None
    dtmf: str | None = None


class HarnessPromptBlock(BaseModel):
    """Harness plays content and may optionally listen for a response."""

    kind: Literal["harness_prompt"] = "harness_prompt"
    id: str
    content: PromptContent
    listen: bool = True
    next: str | None = None
    branching: BranchConfig | None = None
    max_visits: int = Field(default=1, ge=0)
    adversarial: bool = False
    technique: AdversarialTechnique | None = None
    expect: TurnExpectation | None = None
    config: TurnConfig = Field(default_factory=TurnConfig)

    @model_validator(mode="after")
    def validate_content_and_routing(self) -> HarnessPromptBlock:
        populated = [
            value
            for value in (
                self.content.text,
                self.content.audio_file,
                self.content.silence_s,
                self.content.dtmf,
            )
            if value is not None
        ]
        if len(populated) != 1:
            raise ValueError(
                f"harness_prompt block '{self.id}': exactly one content field required"
            )
        if self.branching is not None and self.next is not None:
            raise ValueError(
                f"harness_prompt block '{self.id}': cannot set both branching and next"
            )
        if self.adversarial and self.technique is None:
            raise ValueError(
                f"harness_prompt block '{self.id}': adversarial=true requires a technique"
            )
        return self


class BotListenBlock(BaseModel):
    """Harness waits for the bot to speak first."""

    kind: Literal["bot_listen"] = "bot_listen"
    id: str
    next: str | None = None
    branching: BranchConfig | None = None
    max_visits: int = Field(default=1, ge=0)
    adversarial: bool = False
    technique: AdversarialTechnique | None = None
    expect: TurnExpectation | None = None
    config: TurnConfig = Field(default_factory=TurnConfig)

    @model_validator(mode="after")
    def validate_adversarial(self) -> BotListenBlock:
        if self.adversarial and self.technique is None:
            raise ValueError(
                f"bot_listen block '{self.id}': adversarial=true requires a technique"
            )
        return self


class HangupBlock(BaseModel):
    """Terminal hangup marker."""

    kind: Literal["hangup"] = "hangup"
    id: str
    next: None = None
    branching: None = None
    max_visits: int = Field(default=1, ge=0)
    adversarial: bool = False
    technique: None = None
    expect: None = None
    config: TurnConfig = Field(default_factory=TurnConfig)


class WaitBlock(BaseModel):
    """Clock-only pause that does not emit audio or open a listen window."""

    kind: Literal["wait"] = "wait"
    id: str
    wait_s: float = Field(gt=0.0)
    next: str | None = None
    branching: None = None
    max_visits: int = Field(default=1, ge=0)
    adversarial: bool = False
    technique: None = None
    expect: None = None
    config: TurnConfig = Field(default_factory=TurnConfig)


_TIME_ROUTE_HHMM_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class TimeRouteWindow(BaseModel):
    """Time-of-day route arm within a time_route block."""

    label: str
    start: str
    end: str
    next: str

    @model_validator(mode="after")
    def validate_window(self) -> TimeRouteWindow:
        if not self.label.strip():
            raise ValueError("time_route windows require a non-empty label")
        if not _TIME_ROUTE_HHMM_RE.fullmatch(self.start):
            raise ValueError(
                f"time_route window '{self.label}': start must use HH:MM 24-hour format"
            )
        if not _TIME_ROUTE_HHMM_RE.fullmatch(self.end):
            raise ValueError(
                f"time_route window '{self.label}': end must use HH:MM 24-hour format"
            )
        if self.start == self.end:
            raise ValueError(
                f"time_route window '{self.label}': start and end cannot be identical"
            )
        if not self.next.strip():
            raise ValueError(f"time_route window '{self.label}': next must be non-empty")
        return self


class TimeRouteBlock(BaseModel):
    """Route to the next turn based on local time in a configured timezone."""

    kind: Literal["time_route"] = "time_route"
    id: str
    timezone: str
    windows: list[TimeRouteWindow]
    default: str
    next: None = None
    branching: None = None
    max_visits: int = Field(default=1, ge=0)
    adversarial: bool = False
    technique: None = None
    expect: None = None
    config: TurnConfig = Field(default_factory=TurnConfig)

    @model_validator(mode="after")
    def validate_time_route(self) -> TimeRouteBlock:
        if not self.timezone.strip():
            raise ValueError("time_route timezone must be non-empty")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, KeyError) as exc:
            raise ValueError(f"Invalid time_route timezone: {self.timezone}") from exc
        if not self.windows:
            raise ValueError("time_route windows must contain at least one window")
        if not self.default.strip():
            raise ValueError("time_route default must be non-empty")
        seen_labels: set[str] = set()
        for window in self.windows:
            normalized = window.label.strip().lower()
            if normalized in seen_labels:
                raise ValueError("time_route window labels must be unique")
            seen_labels.add(normalized)
        return self


ScenarioBlock = Annotated[
    HarnessPromptBlock | BotListenBlock | HangupBlock | WaitBlock | TimeRouteBlock,
    Field(discriminator="kind"),
]

SCENARIO_BLOCK_ADAPTER = TypeAdapter(ScenarioBlock)


def normalize_legacy_turn_to_block(raw_turn: dict[str, object]) -> ScenarioBlock:
    """Convert a legacy raw turn mapping into a normalized block."""

    # Builder-authored hangup markers must be checked FIRST on the raw mapping.
    # (a) They do not survive Turn validation (content-less harness turn).
    # (b) A hangup with an erroneous speaker="bot" field should still map to
    #     HangupBlock, not BotListenBlock.
    if raw_turn.get("builder_block") == "hangup":
        turn_id = str(raw_turn.get("id") or "").strip()
        if not turn_id:
            raise ValueError("Legacy hangup block requires a non-empty id")
        return HangupBlock(id=turn_id)

    speaker = raw_turn.get("speaker")
    if speaker == "bot":
        turn = Turn(**raw_turn)
        return BotListenBlock(
            id=turn.id,
            next=turn.next,
            branching=turn.branching,
            max_visits=turn.max_visits,
            adversarial=turn.adversarial,
            technique=turn.technique,
            expect=turn.expect,
            config=turn.config,
        )

    turn = Turn(**raw_turn)
    # Normalize empty/whitespace text to None so that old scenarios with
    # text: "" + silence_s (or other content) satisfy the HarnessPromptBlock
    # "exactly one content field" invariant.
    text_value = turn.text if turn.text and turn.text.strip() else None
    return HarnessPromptBlock(
        id=turn.id,
        content=PromptContent(
            text=text_value,
            audio_file=turn.audio_file,
            silence_s=turn.silence_s,
            dtmf=turn.dtmf,
        ),
        listen=turn.wait_for_response,
        next=turn.next,
        branching=turn.branching,
        max_visits=turn.max_visits,
        adversarial=turn.adversarial,
        technique=turn.technique,
        expect=turn.expect,
        config=turn.config,
    )


def load_block(raw_turn: dict[str, object]) -> ScenarioBlock:
    """Load either a Phase A block payload or a legacy turn payload."""

    if "kind" in raw_turn:
        return SCENARIO_BLOCK_ADAPTER.validate_python(raw_turn)
    return normalize_legacy_turn_to_block(raw_turn)
