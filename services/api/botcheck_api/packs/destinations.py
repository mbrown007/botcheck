from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import write_audit_event
from ..auth import UserContext, require_editor, require_viewer
from ..config import settings
from ..database import get_db
from ..exceptions import (
    ApiProblem,
    DESTINATION_IN_USE,
    DESTINATION_INACTIVE,
    DESTINATION_NOT_FOUND,
    DESTINATIONS_DISABLED,
)
from ..models import DestinationProtocol
from ..text_normalization import strip_nonempty, strip_or_none
from .service import (
    DestinationUsageResult,
    StoredBotDestination,
    StoredSIPTrunk,
    create_or_replace_bot_destination,
    delete_bot_destination,
    get_bot_destination,
    get_destination_usage,
    list_bot_destinations,
    list_destination_usage,
    list_sip_trunks,
)

router = APIRouter()


class DirectHTTPTransportConfig(BaseModel):
    http_mode: Literal["generic_json", "json_sse_chat"] = "generic_json"
    method: Literal["POST"] = "POST"
    request_content_type: Literal["json"] = "json"
    request_text_field: str = Field(default="message", min_length=1, max_length=128)
    request_history_field: str | None = Field(default="history", max_length=128)
    request_session_id_field: str | None = Field(default="session_id", max_length=128)
    request_body_defaults: dict[str, object] = Field(default_factory=dict)
    response_text_field: str = Field(default="response", min_length=1, max_length=128)
    timeout_s: float = Field(default=30.0, gt=0, le=120)
    max_retries: int = Field(default=1, ge=0, le=3)

    @field_validator(
        "request_text_field",
        "request_history_field",
        "request_session_id_field",
        "response_text_field",
    )
    @classmethod
    def _normalize_field_name(cls, value: str | None) -> str | None:
        return strip_or_none(value)

    @field_validator("request_body_defaults", mode="before")
    @classmethod
    def _normalize_request_body_defaults(cls, value: object) -> dict[str, object]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("request_body_defaults must be an object")
        return {str(key): val for key, val in value.items()}


class WebRTCTransportConfig(BaseModel):
    provider: Literal["livekit"] = "livekit"
    session_mode: Literal["bot_builder_preview"] = "bot_builder_preview"
    api_base_url: str = Field(min_length=1, max_length=512)
    agent_id: str = Field(min_length=1, max_length=128)
    version_id: str = Field(min_length=1, max_length=128)
    auth_headers: dict[str, Any] = Field(default_factory=dict)
    join_timeout_s: int = Field(default=20, ge=1, le=120)

    @field_validator("api_base_url")
    @classmethod
    def _normalize_api_base_url(cls, value: str) -> str:
        stripped = value.strip().rstrip("/")
        if not stripped:
            raise ValueError("api_base_url must not be blank")
        if not stripped.lower().startswith("https://"):
            raise ValueError("api_base_url must use the https scheme")
        return stripped

    @field_validator("agent_id", "version_id")
    @classmethod
    def _normalize_required_string(cls, value: str) -> str:
        return strip_nonempty(value, error_message="field must not be blank")

    @field_validator("auth_headers", mode="before")
    @classmethod
    def _normalize_auth_headers(cls, value: dict[str, Any] | None) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("auth_headers must be an object")
        return {
            str(key).strip(): str(val).strip()
            for key, val in value.items()
            if str(key).strip()
        }


class BotDestinationUpsert(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    protocol: DestinationProtocol = DestinationProtocol.MOCK
    endpoint: str | None = Field(default=None, max_length=512)
    default_dial_target: str | None = Field(default=None, max_length=512)
    caller_id: str | None = Field(default=None, max_length=64)
    trunk_id: str | None = Field(default=None, max_length=255)
    trunk_pool_id: str | None = Field(default=None, max_length=64)
    headers: dict[str, Any] = Field(default_factory=dict)
    direct_http_config: DirectHTTPTransportConfig | None = None
    webrtc_config: WebRTCTransportConfig | None = None
    is_active: bool = True
    provisioned_channels: int | None = Field(default=None, ge=1)
    reserved_channels: int | None = Field(default=None, ge=0)
    botcheck_max_channels: int | None = Field(default=None, ge=1)
    capacity_scope: str | None = Field(default=None, max_length=128)

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        return strip_nonempty(value, error_message="name must not be empty")

    @field_validator("endpoint")
    @classmethod
    def _normalize_endpoint(cls, value: str | None) -> str | None:
        return strip_or_none(value)

    @field_validator("default_dial_target")
    @classmethod
    def _normalize_default_dial_target(cls, value: str | None) -> str | None:
        return strip_or_none(value)

    @field_validator("caller_id")
    @classmethod
    def _normalize_caller_id(cls, value: str | None) -> str | None:
        return strip_or_none(value)

    @field_validator("trunk_id")
    @classmethod
    def _normalize_trunk_id(cls, value: str | None) -> str | None:
        return strip_or_none(value)

    @field_validator("trunk_pool_id")
    @classmethod
    def _normalize_trunk_pool_id(cls, value: str | None) -> str | None:
        return strip_or_none(value)

    @field_validator("capacity_scope")
    @classmethod
    def _normalize_capacity_scope(cls, value: str | None) -> str | None:
        return strip_or_none(value)

    @field_validator("headers", mode="before")
    @classmethod
    def _normalize_headers(cls, value: dict[str, Any] | None) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("headers must be an object")
        return {str(key).strip(): str(val).strip() if isinstance(val, str) else val for key, val in value.items()}

    @model_validator(mode="after")
    def _validate_target_fields(self) -> "BotDestinationUpsert":
        endpoint = self.endpoint
        default_dial_target = self.default_dial_target
        if (
            endpoint is not None
            and default_dial_target is not None
            and endpoint != default_dial_target
        ):
            raise ValueError("endpoint and default_dial_target must match when both are provided")
        if self.protocol == DestinationProtocol.HTTP and endpoint is None:
            raise ValueError("endpoint is required for http transport profiles")
        if self.protocol == DestinationProtocol.WEBRTC and self.webrtc_config is None:
            raise ValueError("webrtc_config is required for webrtc transport profiles")
        if self.protocol != DestinationProtocol.HTTP and self.direct_http_config is not None:
            raise ValueError("direct_http_config is only valid for http transport profiles")
        if self.protocol != DestinationProtocol.WEBRTC and self.webrtc_config is not None:
            raise ValueError("webrtc_config is only valid for webrtc transport profiles")
        if self.protocol != DestinationProtocol.SIP and (
            self.trunk_id is not None or self.trunk_pool_id is not None or self.caller_id is not None
        ):
            raise ValueError("trunk and caller fields are only valid for sip transport profiles")
        return self


class BotDestinationResponse(BaseModel):
    destination_id: str
    transport_profile_id: str
    name: str
    protocol: DestinationProtocol
    endpoint: str | None = None
    default_dial_target: str | None = None
    caller_id: str | None = None
    trunk_id: str | None = None
    trunk_pool_id: str | None = None
    headers: dict[str, Any]
    direct_http_config: DirectHTTPTransportConfig | None = None
    webrtc_config: WebRTCTransportConfig | None = None
    is_active: bool
    provisioned_channels: int | None = None
    reserved_channels: int | None = None
    botcheck_max_channels: int | None = None
    capacity_scope: str | None = None
    effective_channels: int | None = None
    active_schedule_count: int = 0
    active_pack_run_count: int = 0
    in_use: bool = False
    created_at: datetime
    updated_at: datetime


class BotDestinationSummaryResponse(BaseModel):
    destination_id: str
    transport_profile_id: str
    name: str
    protocol: DestinationProtocol
    endpoint: str | None = None
    default_dial_target: str | None = None
    caller_id: str | None = None
    trunk_id: str | None = None
    trunk_pool_id: str | None = None
    header_count: int = 0
    direct_http_config: DirectHTTPTransportConfig | None = None
    webrtc_config: WebRTCTransportConfig | None = None
    is_active: bool
    provisioned_channels: int | None = None
    reserved_channels: int | None = None
    botcheck_max_channels: int | None = None
    capacity_scope: str | None = None
    effective_channels: int | None = None
    active_schedule_count: int = 0
    active_pack_run_count: int = 0
    in_use: bool = False
    created_at: datetime
    updated_at: datetime


class SIPTrunkSummaryResponse(BaseModel):
    trunk_id: str
    name: str | None = None
    provider_name: str | None = None
    address: str | None = None
    transport: str | None = None
    numbers: list[str]
    metadata_json: dict[str, Any]
    is_active: bool
    last_synced_at: datetime
    created_at: datetime
    updated_at: datetime


def _require_destinations_enabled() -> None:
    if not settings.feature_destinations_enabled:
        raise ApiProblem(
            status=503,
            error_code=DESTINATIONS_DISABLED,
            detail="Destinations are disabled",
        )


def _usage_counts(usage: DestinationUsageResult | None) -> tuple[int, int, bool]:
    if usage is None:
        return 0, 0, False
    active_schedule_count = len(usage.active_schedule_ids)
    active_pack_run_count = len(usage.active_pack_run_ids)
    return (
        active_schedule_count,
        active_pack_run_count,
        active_schedule_count > 0 or active_pack_run_count > 0,
    )


def _raise_destination_in_use(usage: DestinationUsageResult) -> None:
    schedule_count = len(usage.active_schedule_ids)
    pack_run_count = len(usage.active_pack_run_ids)
    raise ApiProblem(
        status=409,
        error_code=DESTINATION_IN_USE,
        detail=(
            "Destination is in use by active schedules or active pack runs "
            f"(active_schedule_count={schedule_count}, active_pack_run_count={pack_run_count})"
        ),
    )


def _as_destination_response(
    stored: StoredBotDestination,
    *,
    usage: DestinationUsageResult | None = None,
) -> BotDestinationResponse:
    active_schedule_count, active_pack_run_count, in_use = _usage_counts(usage)
    return BotDestinationResponse(
        destination_id=stored.destination_id,
        transport_profile_id=stored.destination_id,
        name=stored.name,
        protocol=DestinationProtocol(stored.protocol),
        endpoint=stored.endpoint,
        default_dial_target=stored.endpoint,
        caller_id=stored.caller_id,
        trunk_id=stored.trunk_id,
        trunk_pool_id=stored.trunk_pool_id,
        headers=stored.headers,
        direct_http_config=stored.direct_http_config,
        webrtc_config=stored.webrtc_config,
        is_active=stored.is_active,
        provisioned_channels=stored.provisioned_channels,
        reserved_channels=stored.reserved_channels,
        botcheck_max_channels=stored.botcheck_max_channels,
        capacity_scope=stored.capacity_scope,
        effective_channels=stored.effective_channels,
        active_schedule_count=active_schedule_count,
        active_pack_run_count=active_pack_run_count,
        in_use=in_use,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
    )


def _as_destination_summary(
    stored: StoredBotDestination,
    *,
    usage: DestinationUsageResult | None = None,
) -> BotDestinationSummaryResponse:
    active_schedule_count, active_pack_run_count, in_use = _usage_counts(usage)
    wc = stored.webrtc_config or {}
    webrtc_config_summary: dict[str, object] | None = (
        {
            "provider": wc.get("provider"),
            "session_mode": wc.get("session_mode"),
            "api_base_url": wc.get("api_base_url"),
            "agent_id": wc.get("agent_id"),
            "version_id": wc.get("version_id"),
            "auth_headers": {},  # always redacted on list endpoint
            "join_timeout_s": wc.get("join_timeout_s"),
        }
        if wc
        else None
    )
    return BotDestinationSummaryResponse(
        destination_id=stored.destination_id,
        transport_profile_id=stored.destination_id,
        name=stored.name,
        protocol=DestinationProtocol(stored.protocol),
        endpoint=stored.endpoint,
        default_dial_target=stored.endpoint,
        caller_id=stored.caller_id,
        trunk_id=stored.trunk_id,
        trunk_pool_id=stored.trunk_pool_id,
        header_count=len(stored.headers),
        direct_http_config=stored.direct_http_config,
        webrtc_config=webrtc_config_summary,
        is_active=stored.is_active,
        provisioned_channels=stored.provisioned_channels,
        reserved_channels=stored.reserved_channels,
        botcheck_max_channels=stored.botcheck_max_channels,
        capacity_scope=stored.capacity_scope,
        effective_channels=stored.effective_channels,
        active_schedule_count=active_schedule_count,
        active_pack_run_count=active_pack_run_count,
        in_use=in_use,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
    )


def _as_sip_trunk_summary(stored: StoredSIPTrunk) -> SIPTrunkSummaryResponse:
    return SIPTrunkSummaryResponse(
        trunk_id=stored.trunk_id,
        name=stored.name,
        provider_name=stored.provider_name,
        address=stored.address,
        transport=stored.transport,
        numbers=stored.numbers,
        metadata_json=stored.metadata_json,
        is_active=stored.is_active,
        last_synced_at=stored.last_synced_at,
        created_at=stored.created_at,
        updated_at=stored.updated_at,
    )


@router.get("/", response_model=list[BotDestinationSummaryResponse])
async def list_destinations(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    _require_destinations_enabled()
    rows = await list_bot_destinations(db, user.tenant_id)
    usage_by_destination = await list_destination_usage(db, user.tenant_id)
    return [
        _as_destination_summary(row, usage=usage_by_destination.get(row.destination_id))
        for row in rows
    ]


@router.get("/trunks", response_model=list[SIPTrunkSummaryResponse])
async def list_trunks(
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    _require_destinations_enabled()
    rows = await list_sip_trunks(db)
    return [_as_sip_trunk_summary(row) for row in rows]


@router.post("/", response_model=BotDestinationResponse, status_code=201)
async def create_destination(
    body: BotDestinationUpsert,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_editor),
):
    _require_destinations_enabled()
    endpoint = body.default_dial_target or body.endpoint
    try:
        stored = await create_or_replace_bot_destination(
            db,
            tenant_id=user.tenant_id,
            name=body.name,
            protocol=body.protocol.value,
            endpoint=endpoint,
            caller_id=body.caller_id,
            trunk_id=body.trunk_id,
            trunk_pool_id=body.trunk_pool_id,
            headers=body.headers,
            direct_http_config=(
                body.direct_http_config.model_dump(mode="json")
                if body.direct_http_config is not None
                else None
            ),
            webrtc_config=(
                body.webrtc_config.model_dump(mode="json")
                if body.webrtc_config is not None
                else None
            ),
            is_active=body.is_active,
            provisioned_channels=body.provisioned_channels,
            reserved_channels=body.reserved_channels,
            botcheck_max_channels=body.botcheck_max_channels,
            capacity_scope=body.capacity_scope,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        action="destinations.create",
        resource_type="destination",
        resource_id=stored.destination_id,
        detail={
            "name": stored.name,
            "protocol": stored.protocol,
            "is_active": stored.is_active,
            "trunk_pool_id": stored.trunk_pool_id,
            "capacity_scope": stored.capacity_scope,
            "effective_channels": stored.effective_channels,
        },
    )
    await db.commit()
    return _as_destination_response(stored)


@router.get("/{destination_id}", response_model=BotDestinationResponse)
async def get_destination(
    destination_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_viewer),
):
    _require_destinations_enabled()
    stored = await get_bot_destination(db, destination_id, user.tenant_id)
    if stored is None:
        raise ApiProblem(
            status=404,
            error_code=DESTINATION_NOT_FOUND,
            detail="Destination not found",
        )
    usage = await get_destination_usage(db, destination_id, user.tenant_id)
    return _as_destination_response(stored, usage=usage)


@router.put("/{destination_id}", response_model=BotDestinationResponse)
async def update_destination(
    destination_id: str,
    body: BotDestinationUpsert,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_editor),
):
    _require_destinations_enabled()
    existing = await get_bot_destination(db, destination_id, user.tenant_id)
    if existing is None:
        raise ApiProblem(
            status=404,
            error_code=DESTINATION_NOT_FOUND,
            detail="Destination not found",
        )
    if existing.is_active and not body.is_active:
        usage = await get_destination_usage(db, destination_id, user.tenant_id)
        if usage.active_schedule_ids or usage.active_pack_run_ids:
            _raise_destination_in_use(usage)
    endpoint = body.default_dial_target or body.endpoint
    try:
        stored = await create_or_replace_bot_destination(
            db,
            destination_id=destination_id,
            tenant_id=user.tenant_id,
            name=body.name,
            protocol=body.protocol.value,
            endpoint=endpoint,
            caller_id=body.caller_id,
            trunk_id=body.trunk_id,
            trunk_pool_id=body.trunk_pool_id,
            headers=body.headers,
            direct_http_config=(
                body.direct_http_config.model_dump(mode="json")
                if body.direct_http_config is not None
                else None
            ),
            webrtc_config=(
                body.webrtc_config.model_dump(mode="json")
                if body.webrtc_config is not None
                else None
            ),
            is_active=body.is_active,
            provisioned_channels=body.provisioned_channels,
            reserved_channels=body.reserved_channels,
            botcheck_max_channels=body.botcheck_max_channels,
            capacity_scope=body.capacity_scope,
        )
    except LookupError as exc:
        raise ApiProblem(
            status=404,
            error_code=DESTINATION_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        action="destinations.update",
        resource_type="destination",
        resource_id=stored.destination_id,
        detail={
            "name": stored.name,
            "protocol": stored.protocol,
            "is_active": stored.is_active,
            "trunk_pool_id": stored.trunk_pool_id,
            "capacity_scope": stored.capacity_scope,
            "effective_channels": stored.effective_channels,
        },
    )
    await db.commit()
    usage = await get_destination_usage(db, destination_id, user.tenant_id)
    return _as_destination_response(stored, usage=usage)


@router.delete("/{destination_id}", status_code=204)
async def delete_destination(
    destination_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(require_editor),
):
    _require_destinations_enabled()
    stored = await get_bot_destination(db, destination_id, user.tenant_id)
    if stored is None:
        raise ApiProblem(
            status=404,
            error_code=DESTINATION_NOT_FOUND,
            detail="Destination not found",
        )
    usage = await get_destination_usage(db, destination_id, user.tenant_id)
    if usage.active_schedule_ids or usage.active_pack_run_ids:
        _raise_destination_in_use(usage)
    deleted = await delete_bot_destination(db, destination_id, user.tenant_id)
    if not deleted:
        raise ApiProblem(
            status=404,
            error_code=DESTINATION_NOT_FOUND,
            detail="Destination not found",
        )
    await write_audit_event(
        db,
        tenant_id=user.tenant_id,
        actor_id=user.sub,
        action="destinations.delete",
        resource_type="destination",
        resource_id=destination_id,
        detail={},
    )
    await db.commit()
