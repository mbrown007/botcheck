"""Named tuple models for pack feature services."""

from __future__ import annotations

from datetime import datetime
from typing import Any, NamedTuple


class StoredScenarioPackItem(NamedTuple):
    scenario_id: str
    ai_scenario_id: str | None
    order_index: int


class StoredScenarioPack(NamedTuple):
    pack_id: str
    name: str
    description: str | None
    tags: list[str]
    execution_mode: str
    created_at: datetime
    updated_at: datetime
    items: list[StoredScenarioPackItem]


class StoredBotDestination(NamedTuple):
    destination_id: str
    tenant_id: str
    name: str
    protocol: str
    endpoint: str | None
    caller_id: str | None
    trunk_id: str | None
    trunk_pool_id: str | None
    headers: dict[str, Any]
    direct_http_config: dict[str, Any] | None
    webrtc_config: dict[str, Any] | None
    is_active: bool
    provisioned_channels: int | None
    reserved_channels: int | None
    botcheck_max_channels: int | None
    capacity_scope: str | None
    effective_channels: int | None
    created_at: datetime
    updated_at: datetime


class DiscoveredSIPTrunk(NamedTuple):
    trunk_id: str
    name: str | None
    provider_name: str | None
    address: str | None
    transport: str | None
    numbers: list[str]
    metadata_json: dict[str, Any]


class StoredSIPTrunk(NamedTuple):
    trunk_id: str
    name: str | None
    provider_name: str | None
    address: str | None
    transport: str | None
    numbers: list[str]
    metadata_json: dict[str, Any]
    is_active: bool
    last_synced_at: datetime
    created_at: datetime
    updated_at: datetime


class DestinationUsageResult(NamedTuple):
    active_schedule_ids: list[str]
    active_pack_run_ids: list[str]


class PackRunSnapshot(NamedTuple):
    pack_run_id: str
    pack_id: str
    tenant_id: str
    destination_id: str | None
    transport_profile_id: str | None
    dial_target: str | None
    state: str
    total_scenarios: int


class PackRunDispatchStartResult(NamedTuple):
    found: bool
    applied: bool
    state: str
    reason: str
    tenant_id: str | None


class PackRunCancelResult(NamedTuple):
    found: bool
    applied: bool
    state: str
    reason: str
    tenant_id: str | None


class PackRunMarkFailedResult(NamedTuple):
    found: bool
    applied: bool
    state: str
    reason: str
    tenant_id: str | None


class PackRunChildAggregateResult(NamedTuple):
    found: bool
    applied: bool
    pack_run_id: str | None
    item_state: str | None
    pack_run_state: str | None
    reason: str
