"""SIP trunk registry discovery and read-model services."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from livekit import api as lk_api
from sqlalchemy.ext.asyncio import AsyncSession

from .. import repo_runs as runs_repo
from ..config import Settings, settings
from ..models import SIPTrunkRow
from .service_models import DiscoveredSIPTrunk, StoredSIPTrunk


def _list_sip_outbound_trunk_request_cls():
    request_cls = getattr(lk_api, "ListSIPOutboundTrunkRequest", None)
    if request_cls is not None:
        return request_cls

    sip_namespace = getattr(lk_api, "sip", None)
    if sip_namespace is not None:
        request_cls = getattr(sip_namespace, "ListSIPOutboundTrunkRequest", None)
        if request_cls is not None:
            return request_cls

    raise AttributeError("LiveKit SDK missing ListSIPOutboundTrunkRequest")


def _to_str(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_string_list(values: object | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, (list, tuple)):
        return [candidate for candidate in (_to_str(v) for v in values) if candidate]
    candidate = _to_str(values)
    return [candidate] if candidate else []


def _extract_numbers(payload: object) -> list[str]:
    for attr in ("numbers", "allowed_numbers", "phone_numbers"):
        values = getattr(payload, attr, None)
        out = _to_string_list(values)
        if out:
            return out
    return []


def _extract_metadata(payload: object) -> dict[str, Any]:
    raw = getattr(payload, "metadata", None)
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items()}
    text = _to_str(raw)
    if text is None:
        return {}
    return {"raw": text}


def _extract_provider_name(address: str | None) -> str | None:
    if address is None or "@" in address:
        return None
    return address


def _normalize_trunk_payload(payload: object) -> DiscoveredSIPTrunk:
    trunk_id = _to_str(getattr(payload, "sip_trunk_id", None) or getattr(payload, "trunk_id", None))
    if trunk_id is None:
        raise ValueError("LiveKit outbound SIP trunk payload missing trunk_id")
    address = _to_str(getattr(payload, "address", None))
    return DiscoveredSIPTrunk(
        trunk_id=trunk_id,
        name=_to_str(getattr(payload, "name", None)),
        provider_name=_extract_provider_name(address),
        address=address,
        transport=_to_str(getattr(payload, "transport", None)),
        numbers=_extract_numbers(payload),
        metadata_json=_extract_metadata(payload),
    )


async def discover_livekit_sip_trunks(
    *,
    settings_obj: Settings = settings,
    livekit_api_cls=lk_api.LiveKitAPI,
) -> list[DiscoveredSIPTrunk]:
    request = _list_sip_outbound_trunk_request_cls()()
    async with livekit_api_cls(
        url=settings_obj.livekit_url,
        api_key=settings_obj.livekit_api_key,
        api_secret=settings_obj.livekit_api_secret,
    ) as livekit_api:
        sip_service = livekit_api.sip
        list_method = getattr(sip_service, "list_outbound_trunk", None)
        if list_method is None:
            list_method = getattr(sip_service, "list_sip_outbound_trunk", None)
        if list_method is None:
            raise AttributeError("LiveKit SDK missing SIP trunk list method")
        response = await list_method(request)

    items = getattr(response, "items", None)
    if items is None and isinstance(response, list):
        items = response
    if items is None:
        items = []
    return [_normalize_trunk_payload(item) for item in items]


def _as_stored_sip_trunk(row: SIPTrunkRow) -> StoredSIPTrunk:
    return StoredSIPTrunk(
        trunk_id=row.trunk_id,
        name=row.name,
        provider_name=row.provider_name,
        address=row.address,
        transport=row.transport,
        numbers=list(row.numbers or []),
        metadata_json=dict(row.metadata_json or {}),
        is_active=bool(row.is_active),
        last_synced_at=row.last_synced_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def sync_sip_trunks(
    db: AsyncSession,
    *,
    discovered: list[DiscoveredSIPTrunk] | None = None,
    settings_obj: Settings = settings,
    livekit_api_cls=lk_api.LiveKitAPI,
) -> list[StoredSIPTrunk]:
    discovered_trunks = discovered
    if discovered_trunks is None:
        discovered_trunks = await discover_livekit_sip_trunks(
            settings_obj=settings_obj,
            livekit_api_cls=livekit_api_cls,
        )

    existing_rows = await runs_repo.list_sip_trunk_rows(db)
    existing_by_id = {row.trunk_id: row for row in existing_rows}
    seen_ids: set[str] = set()
    now = datetime.now(UTC)

    for trunk in discovered_trunks:
        seen_ids.add(trunk.trunk_id)
        row = existing_by_id.get(trunk.trunk_id)
        if row is None:
            row = SIPTrunkRow(
                trunk_id=trunk.trunk_id,
                name=trunk.name,
                provider_name=trunk.provider_name,
                address=trunk.address,
                transport=trunk.transport,
                numbers=trunk.numbers,
                metadata_json=trunk.metadata_json,
                is_active=True,
                last_synced_at=now,
            )
            await runs_repo.upsert_sip_trunk_row(db, row)
            existing_by_id[trunk.trunk_id] = row
            continue

        row.name = trunk.name
        row.provider_name = trunk.provider_name
        row.address = trunk.address
        row.transport = trunk.transport
        row.numbers = trunk.numbers
        row.metadata_json = trunk.metadata_json
        row.is_active = True
        row.last_synced_at = now

    for trunk_id, row in existing_by_id.items():
        if trunk_id in seen_ids:
            continue
        row.is_active = False
        row.last_synced_at = now

    await db.flush()
    rows = await runs_repo.list_sip_trunk_rows(db)
    return [_as_stored_sip_trunk(row) for row in rows]


async def list_sip_trunks(db: AsyncSession) -> list[StoredSIPTrunk]:
    rows = await runs_repo.list_sip_trunk_rows(db)
    return [_as_stored_sip_trunk(row) for row in rows]


async def get_sip_trunk(db: AsyncSession, *, trunk_id: str) -> StoredSIPTrunk | None:
    row = await runs_repo.get_sip_trunk_row(db, trunk_id)
    if row is None:
        return None
    return _as_stored_sip_trunk(row)
