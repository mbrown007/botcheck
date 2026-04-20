"""Destination business logic for packs feature."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from .. import repo_packs as packs_repo
from .. import repo_runs as runs_repo
from ..capacity import DEFAULT_SIP_CAPACITY_SCOPE
from ..models import BotDestinationRow, DestinationProtocol, PackRunState
from .service_models import DestinationUsageResult, StoredBotDestination


def _effective_bot_destination_capacity(
    *,
    protocol: str,
    is_active: bool,
    provisioned_channels: int | None,
    reserved_channels: int | None,
    botcheck_max_channels: int | None,
) -> int | None:
    if protocol != DestinationProtocol.SIP.value:
        return None
    if botcheck_max_channels is not None:
        raw = botcheck_max_channels
    elif provisioned_channels is not None and reserved_channels is not None:
        raw = provisioned_channels - reserved_channels
    else:
        return None
    if is_active:
        return max(1, raw)
    return max(0, raw)


def _as_stored_bot_destination(row: BotDestinationRow) -> StoredBotDestination:
    return StoredBotDestination(
        destination_id=row.destination_id,
        tenant_id=row.tenant_id,
        name=row.name,
        protocol=row.protocol,
        endpoint=row.endpoint,
        caller_id=row.caller_id,
        trunk_id=row.trunk_id,
        trunk_pool_id=row.trunk_pool_id,
        headers=dict(row.headers or {}),
        direct_http_config=dict(row.direct_http_config or {}) or None,
        webrtc_config=dict(row.webrtc_config or {}) or None,
        is_active=bool(row.is_active),
        provisioned_channels=row.provisioned_channels,
        reserved_channels=row.reserved_channels,
        botcheck_max_channels=row.botcheck_max_channels,
        capacity_scope=row.capacity_scope,
        effective_channels=_effective_bot_destination_capacity(
            protocol=row.protocol,
            is_active=bool(row.is_active),
            provisioned_channels=row.provisioned_channels,
            reserved_channels=row.reserved_channels,
            botcheck_max_channels=row.botcheck_max_channels,
        ),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _validate_bot_destination_payload(
    *,
    protocol: str,
    endpoint: str | None,
    trunk_id: str | None,
    trunk_pool_id: str | None,
    direct_http_config: dict[str, Any] | None,
    webrtc_config: dict[str, Any] | None,
    provisioned_channels: int | None,
    reserved_channels: int | None,
    botcheck_max_channels: int | None,
    capacity_scope: str | None,
) -> None:
    if protocol == DestinationProtocol.HTTP.value:
        if endpoint is None or not endpoint.strip():
            raise ValueError("endpoint is required for http transport profiles")
        if direct_http_config is not None and not isinstance(direct_http_config, dict):
            raise ValueError("direct_http_config must be an object")
        if webrtc_config is not None:
            raise ValueError("webrtc_config is only valid for webrtc transport profiles")
    if protocol == DestinationProtocol.WEBRTC.value:
        if webrtc_config is None:
            raise ValueError("webrtc_config is required for webrtc transport profiles")
        if not isinstance(webrtc_config, dict):
            raise ValueError("webrtc_config must be an object")
        if direct_http_config is not None:
            raise ValueError("direct_http_config is only valid for http transport profiles")
    if protocol != DestinationProtocol.SIP.value:
        if (
            provisioned_channels is not None
            or reserved_channels is not None
            or botcheck_max_channels is not None
            or capacity_scope is not None
            or trunk_id is not None
            or trunk_pool_id is not None
        ):
            raise ValueError("capacity, trunk, and caller fields are only valid for sip destinations")
        if protocol != DestinationProtocol.HTTP.value and direct_http_config is not None:
            raise ValueError("direct_http_config is only valid for http transport profiles")
        if protocol != DestinationProtocol.WEBRTC.value and webrtc_config is not None:
            raise ValueError("webrtc_config is only valid for webrtc transport profiles")
        return
    if endpoint is not None and not endpoint.strip():
        raise ValueError("endpoint must not be blank")
    if (
        provisioned_channels is not None
        and reserved_channels is not None
        and reserved_channels > provisioned_channels
    ):
        raise ValueError("reserved_channels must be <= provisioned_channels")


async def _validate_shared_trunk_scope_invariant(
    db: AsyncSession,
    *,
    tenant_id: str,
    destination_id: str | None,
    protocol: str,
    trunk_id: str | None,
    capacity_scope: str | None,
) -> None:
    if protocol != DestinationProtocol.SIP.value or not trunk_id:
        return
    incoming_effective_scope = capacity_scope or DEFAULT_SIP_CAPACITY_SCOPE
    peers = await runs_repo.list_bot_destination_rows_for_tenant(db, tenant_id)
    for peer in peers:
        if peer.destination_id == destination_id:
            continue
        if peer.protocol != DestinationProtocol.SIP.value or peer.trunk_id != trunk_id:
            continue
        peer_effective_scope = peer.capacity_scope or DEFAULT_SIP_CAPACITY_SCOPE
        if peer_effective_scope != incoming_effective_scope:
            raise ValueError(
                "destinations sharing the same trunk_id must use the same effective capacity scope"
            )


async def list_bot_destinations(
    db: AsyncSession,
    tenant_id: str,
) -> list[StoredBotDestination]:
    rows = await runs_repo.list_bot_destination_rows_for_tenant(db, tenant_id)
    return [_as_stored_bot_destination(row) for row in rows]


async def get_bot_destination(
    db: AsyncSession,
    destination_id: str,
    tenant_id: str,
) -> StoredBotDestination | None:
    row = await runs_repo.get_bot_destination_row_for_tenant(db, destination_id, tenant_id)
    if row is None:
        return None
    return _as_stored_bot_destination(row)


async def create_or_replace_bot_destination(
    db: AsyncSession,
    *,
    tenant_id: str,
    name: str,
    protocol: str,
    endpoint: str | None,
    caller_id: str | None,
    trunk_id: str | None,
    trunk_pool_id: str | None,
    headers: dict[str, Any],
    direct_http_config: dict[str, Any] | None,
    webrtc_config: dict[str, Any] | None,
    is_active: bool,
    provisioned_channels: int | None,
    reserved_channels: int | None,
    botcheck_max_channels: int | None,
    capacity_scope: str | None,
    destination_id: str | None = None,
) -> StoredBotDestination:
    _validate_bot_destination_payload(
        protocol=protocol,
        endpoint=endpoint,
        trunk_id=trunk_id,
        trunk_pool_id=trunk_pool_id,
        direct_http_config=direct_http_config,
        webrtc_config=webrtc_config,
        provisioned_channels=provisioned_channels,
        reserved_channels=reserved_channels,
        botcheck_max_channels=botcheck_max_channels,
        capacity_scope=capacity_scope,
    )
    await _validate_shared_trunk_scope_invariant(
        db,
        tenant_id=tenant_id,
        destination_id=destination_id,
        protocol=protocol,
        trunk_id=trunk_id,
        capacity_scope=capacity_scope,
    )

    row: BotDestinationRow | None
    if destination_id is None:
        row = None
    else:
        row = await runs_repo.get_bot_destination_row_for_tenant(db, destination_id, tenant_id)
        if row is None:
            raise LookupError("Destination not found")

    existing_by_name = await runs_repo.get_bot_destination_row_by_name_for_tenant(
        db,
        tenant_id=tenant_id,
        name=name,
    )
    if existing_by_name is not None and (
        row is None or existing_by_name.destination_id != row.destination_id
    ):
        raise ValueError("Destination name already exists")

    if row is None:
        row = BotDestinationRow(
            destination_id=f"dest_{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            name=name,
            protocol=protocol,
            endpoint=endpoint,
            caller_id=caller_id,
            trunk_id=trunk_id,
            trunk_pool_id=trunk_pool_id,
            headers=headers,
            direct_http_config=direct_http_config,
            webrtc_config=webrtc_config,
            is_active=is_active,
            provisioned_channels=provisioned_channels,
            reserved_channels=reserved_channels,
            botcheck_max_channels=botcheck_max_channels,
            capacity_scope=capacity_scope,
        )
        await runs_repo.add_bot_destination_row(db, row)
        await db.flush()
        return _as_stored_bot_destination(row)

    row.name = name
    row.protocol = protocol
    row.endpoint = endpoint
    row.caller_id = caller_id
    row.trunk_id = trunk_id
    row.trunk_pool_id = trunk_pool_id
    row.headers = headers
    row.direct_http_config = direct_http_config
    row.webrtc_config = webrtc_config
    row.is_active = is_active
    row.provisioned_channels = provisioned_channels
    row.reserved_channels = reserved_channels
    row.botcheck_max_channels = botcheck_max_channels
    row.capacity_scope = capacity_scope
    return _as_stored_bot_destination(row)


async def delete_bot_destination(
    db: AsyncSession,
    destination_id: str,
    tenant_id: str,
) -> bool:
    return await runs_repo.delete_bot_destination_row_for_tenant(db, destination_id, tenant_id)


async def get_destination_usage(
    db: AsyncSession,
    destination_id: str,
    tenant_id: str,
) -> DestinationUsageResult:
    active_schedule_ids = await runs_repo.list_active_schedule_ids_for_destination_for_tenant(
        db,
        tenant_id=tenant_id,
        destination_id=destination_id,
    )
    active_pack_run_ids = await packs_repo.list_active_pack_run_ids_for_destination_for_tenant(
        db,
        tenant_id=tenant_id,
        destination_id=destination_id,
    )
    return DestinationUsageResult(
        active_schedule_ids=active_schedule_ids,
        active_pack_run_ids=active_pack_run_ids,
    )


async def list_destination_usage(
    db: AsyncSession,
    tenant_id: str,
) -> dict[str, DestinationUsageResult]:
    schedule_rows = await runs_repo.list_schedule_rows_for_tenant(db, tenant_id)
    active_schedule_ids_by_destination: dict[str, list[str]] = {}
    for row in schedule_rows:
        if not row.active:
            continue
        overrides = row.config_overrides
        if not isinstance(overrides, dict):
            continue
        override_destination = str(overrides.get("destination_id", "") or "").strip()
        if override_destination:
            active_schedule_ids_by_destination.setdefault(override_destination, []).append(
                row.schedule_id
            )

    active_states = {PackRunState.PENDING.value, PackRunState.RUNNING.value}
    pack_runs = await packs_repo.list_pack_run_rows_for_tenant(db, tenant_id)
    active_pack_run_ids_by_destination: dict[str, list[str]] = {}
    for row in pack_runs:
        if row.state not in active_states:
            continue
        destination_id = str(row.destination_id or "").strip()
        if not destination_id:
            continue
        active_pack_run_ids_by_destination.setdefault(destination_id, []).append(row.pack_run_id)

    destination_ids = set(active_schedule_ids_by_destination.keys()) | set(
        active_pack_run_ids_by_destination.keys()
    )
    out: dict[str, DestinationUsageResult] = {}
    for destination_id in destination_ids:
        out[destination_id] = DestinationUsageResult(
            active_schedule_ids=active_schedule_ids_by_destination.get(destination_id, []),
            active_pack_run_ids=active_pack_run_ids_by_destination.get(destination_id, []),
        )
    return out
