from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PackRunSummaryResponse(BaseModel):
    pack_run_id: str
    pack_id: str
    destination_id: str | None = None
    transport_profile_id: str | None = None
    dial_target: str | None = None
    state: str
    trigger_source: str
    schedule_id: str | None = None
    triggered_by: str | None = None
    gate_outcome: str
    total_scenarios: int
    dispatched: int
    completed: int
    passed: int
    blocked: int
    failed: int
    created_at: datetime
    updated_at: datetime


class DimensionHeatmapEntry(BaseModel):
    avg_score: float | None = None
    fail_count: int = 0


class PackRunDetailResponse(PackRunSummaryResponse):
    pack_name: str | None = None
    dimension_heatmap: dict[str, DimensionHeatmapEntry] = Field(default_factory=dict)
    previous_pack_run_id: str | None = None
    previous_dimension_heatmap: dict[str, DimensionHeatmapEntry] = Field(default_factory=dict)
    cost_pence: int | None = None


class PackRunChildSummaryResponse(BaseModel):
    pack_run_item_id: str
    scenario_id: str
    ai_scenario_id: str | None = None
    order_index: int
    scenario_version_hash: str
    state: str
    run_id: str | None = None
    run_state: str | None = None
    gate_result: str | None = None
    overall_status: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    failure_category: Literal["dispatch_error", "run_error", "gate_blocked"] | None = None
    summary: str | None = None
    duration_s: float | None = None
    cost_pence: int | None = None
    created_at: datetime | None = None


class PackRunChildrenResponse(BaseModel):
    pack_run_id: str
    total: int
    ai_latency_summary: dict[str, float | int | None] | None = None
    items: list[PackRunChildSummaryResponse]


class PackRunCancelResponse(BaseModel):
    pack_run_id: str
    applied: bool
    state: str
    reason: str


class PackRunMarkFailedRequest(BaseModel):
    reason: str | None = None


class PackRunMarkFailedResponse(BaseModel):
    pack_run_id: str
    applied: bool
    state: str
    reason: str
