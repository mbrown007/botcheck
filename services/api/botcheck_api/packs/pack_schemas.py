from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

from ..text_normalization import strip_nonempty, strip_or_none


class ExecutionMode(str, Enum):
    PARALLEL = "parallel"


class ScenarioPackItemUpsert(BaseModel):
    scenario_id: str | None = None
    ai_scenario_id: str | None = None

    @field_validator("scenario_id", "ai_scenario_id")
    @classmethod
    def _normalize_ids(cls, value: str | None) -> str | None:
        return strip_or_none(value)

    @field_validator("ai_scenario_id")
    @classmethod
    def _ai_feature_guard(cls, value: str | None) -> str | None:
        return value

    @field_validator("scenario_id")
    @classmethod
    def _scenario_feature_guard(cls, value: str | None) -> str | None:
        return value

    @model_validator(mode="after")
    def _require_one_target(self) -> "ScenarioPackItemUpsert":
        if self.scenario_id is None and self.ai_scenario_id is None:
            raise ValueError("pack item requires scenario_id or ai_scenario_id")
        return self


class ScenarioPackUpsert(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    execution_mode: ExecutionMode = ExecutionMode.PARALLEL
    scenario_ids: list[str] = Field(default_factory=list)
    items: list[ScenarioPackItemUpsert] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        return strip_nonempty(value, error_message="name must not be empty")

    @field_validator("description")
    @classmethod
    def _normalize_description(cls, value: str | None) -> str | None:
        return strip_or_none(value)

    @field_validator("tags", mode="before")
    @classmethod
    def _normalize_tags(cls, value: list[str] | str | None) -> list[str]:
        if value is None:
            return []
        tags: list[str]
        if isinstance(value, str):
            tags = [part.strip() for part in value.split(",")]
        else:
            tags = [str(tag).strip() for tag in value]
        deduped: list[str] = []
        seen: set[str] = set()
        for tag in tags:
            if not tag:
                continue
            lowered = tag.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(tag)
        return deduped

    @field_validator("scenario_ids", mode="before")
    @classmethod
    def _normalize_scenario_ids(cls, value: list[str] | str | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            ids = [part.strip() for part in value.split(",")]
        else:
            ids = [str(item).strip() for item in value]
        return [scenario_id for scenario_id in ids if scenario_id]


class ScenarioPackItemResponse(BaseModel):
    scenario_id: str
    ai_scenario_id: str | None = None
    order_index: int


class ScenarioPackSummaryResponse(BaseModel):
    pack_id: str
    name: str
    description: str | None = None
    tags: list[str]
    execution_mode: ExecutionMode
    scenario_count: int


class ScenarioPackDetailResponse(ScenarioPackSummaryResponse):
    items: list[ScenarioPackItemResponse]


class PackRunStartResponse(BaseModel):
    pack_run_id: str
    state: str
    total_scenarios: int
    destination_id: str | None = None
    transport_profile_id: str | None = None
    dial_target: str | None = None


class InternalDispatchPackRunResponse(BaseModel):
    pack_run_id: str
    found: bool
    applied: bool
    state: str
    reason: str


class PackRunStartRequest(BaseModel):
    destination_id: str | None = None
    transport_profile_id: str | None = None
    bot_endpoint: str | None = None
    dial_target: str | None = None

    @field_validator("destination_id", "transport_profile_id", "bot_endpoint", "dial_target")
    @classmethod
    def _normalize_destination_id(cls, value: str | None) -> str | None:
        return strip_or_none(value)

    @model_validator(mode="after")
    def _validate_compatibility(self) -> "PackRunStartRequest":
        if (
            self.destination_id is not None
            and self.transport_profile_id is not None
            and self.destination_id != self.transport_profile_id
        ):
            raise ValueError("destination_id does not match transport_profile_id")
        if (
            self.bot_endpoint is not None
            and self.dial_target is not None
            and self.bot_endpoint != self.dial_target
        ):
            raise ValueError("bot_endpoint does not match dial_target")
        return self


class PackChildRunCreate(BaseModel):
    scenario_id: str
    bot_endpoint: str | None = None
    destination_id: str | None = None
    dial_target: str | None = None
    transport_profile_id: str | None = None
    retention_profile: object | None = None
