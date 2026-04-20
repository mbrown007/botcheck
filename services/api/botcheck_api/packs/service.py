"""Packs feature service facade.

Canonical implementations now live in focused modules:
- service_models.py
- service_destinations.py
- service_packs.py
- service_pack_runs.py
"""

from __future__ import annotations

from .service_destinations import (
    create_or_replace_bot_destination,
    delete_bot_destination,
    get_bot_destination,
    get_destination_usage,
    list_bot_destinations,
    list_destination_usage,
)
from .service_models import (
    DestinationUsageResult,
    DiscoveredSIPTrunk,
    PackRunCancelResult,
    PackRunChildAggregateResult,
    PackRunDispatchStartResult,
    PackRunMarkFailedResult,
    PackRunSnapshot,
    StoredBotDestination,
    StoredSIPTrunk,
    StoredScenarioPack,
    StoredScenarioPackItem,
)
from .service_pack_runs import (
    aggregate_pack_run_child_terminal_state,
    cancel_pack_run,
    create_pack_run_snapshot,
    get_active_pack_run_by_idempotency,
    get_pack_run_for_tenant,
    get_previous_pack_run_for_tenant_pack,
    list_pack_run_items,
    list_pack_runs_for_tenant,
    mark_pack_run_failed,
    start_pack_run_dispatch,
)
from ..runs.store_service import list_runs_by_ids
from .service_packs import (
    create_or_replace_scenario_pack,
    delete_scenario_pack,
    get_scenario_pack,
    has_active_pack_runs_for_pack,
    list_scenario_packs,
)
from .service_sip_trunks import (
    discover_livekit_sip_trunks,
    list_sip_trunks,
    sync_sip_trunks,
)

__all__ = [
    "StoredScenarioPack",
    "StoredScenarioPackItem",
    "StoredBotDestination",
    "DestinationUsageResult",
    "PackRunSnapshot",
    "PackRunDispatchStartResult",
    "PackRunCancelResult",
    "PackRunMarkFailedResult",
    "PackRunChildAggregateResult",
    "create_or_replace_scenario_pack",
    "list_scenario_packs",
    "get_scenario_pack",
    "delete_scenario_pack",
    "has_active_pack_runs_for_pack",
    "create_pack_run_snapshot",
    "start_pack_run_dispatch",
    "cancel_pack_run",
    "mark_pack_run_failed",
    "aggregate_pack_run_child_terminal_state",
    "list_pack_runs_for_tenant",
    "list_pack_run_items",
    "list_runs_by_ids",
    "get_pack_run_for_tenant",
    "get_previous_pack_run_for_tenant_pack",
    "get_active_pack_run_by_idempotency",
    "create_or_replace_bot_destination",
    "list_bot_destinations",
    "get_bot_destination",
    "delete_bot_destination",
    "get_destination_usage",
    "list_destination_usage",
    "DiscoveredSIPTrunk",
    "StoredSIPTrunk",
    "discover_livekit_sip_trunks",
    "list_sip_trunks",
    "sync_sip_trunks",
]
