from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import write_audit_event
from ..models import SIPTrunkRow, TenantRow, TenantTrunkPoolRow, TrunkPoolMemberRow, TrunkPoolRow


@dataclass(frozen=True)
class AdminTrunkPoolMemberRecord:
    member: TrunkPoolMemberRow
    trunk: SIPTrunkRow | None


@dataclass(frozen=True)
class AdminTrunkPoolRecord:
    pool: TrunkPoolRow
    members: list[AdminTrunkPoolMemberRecord]
    assignments: list[TenantTrunkPoolRow]


def _pool_id() -> str:
    return f"pool_{uuid4().hex[:12]}"


def _member_id() -> str:
    return f"pool_member_{uuid4().hex[:12]}"


def _assignment_id() -> str:
    return f"tenant_pool_{uuid4().hex[:12]}"


def _normalized_assignment_quota(
    *,
    max_channels: int | None,
    reserved_channels: int | None,
) -> tuple[int | None, int | None]:
    if max_channels is not None and max_channels < 1:
        raise ValueError("max_channels must be greater than or equal to 1")
    if reserved_channels is not None and reserved_channels < 0:
        raise ValueError("reserved_channels must be greater than or equal to 0")
    if (
        max_channels is not None
        and reserved_channels is not None
        and reserved_channels > max_channels
    ):
        raise ValueError("reserved_channels must be less than or equal to max_channels")
    return max_channels, reserved_channels


async def list_admin_sip_pools(db: AsyncSession) -> list[AdminTrunkPoolRecord]:
    pools = (
        await db.execute(select(TrunkPoolRow).order_by(TrunkPoolRow.created_at.desc(), TrunkPoolRow.name.asc()))
    ).scalars().all()
    return [await get_admin_sip_pool_record(db, pool.trunk_pool_id) for pool in pools]


async def get_admin_sip_pool_record(
    db: AsyncSession,
    trunk_pool_id: str,
) -> AdminTrunkPoolRecord:
    pool = await db.get(TrunkPoolRow, trunk_pool_id)
    if pool is None:
        raise LookupError("Trunk pool not found")
    members = (
        await db.execute(
            select(TrunkPoolMemberRow)
            .where(TrunkPoolMemberRow.trunk_pool_id == trunk_pool_id)
            .order_by(TrunkPoolMemberRow.priority.asc(), TrunkPoolMemberRow.trunk_id.asc())
        )
    ).scalars().all()
    assignments = (
        await db.execute(
            select(TenantTrunkPoolRow)
            .where(TenantTrunkPoolRow.trunk_pool_id == trunk_pool_id)
            .order_by(TenantTrunkPoolRow.tenant_id.asc())
        )
    ).scalars().all()
    trunks_by_id = {
        trunk.trunk_id: trunk
        for trunk in (
            await db.execute(
                select(SIPTrunkRow).where(SIPTrunkRow.trunk_id.in_([member.trunk_id for member in members]))
            )
        ).scalars().all()
    }
    return AdminTrunkPoolRecord(
        pool=pool,
        members=[
            AdminTrunkPoolMemberRecord(member=member, trunk=trunks_by_id.get(member.trunk_id))
            for member in members
        ],
        assignments=list(assignments),
    )


async def create_admin_sip_pool(
    db: AsyncSession,
    *,
    name: str,
    provider_name: str,
    actor_id: str,
    actor_tenant_id: str,
) -> AdminTrunkPoolRecord:
    normalized_name = str(name or "").strip()
    normalized_provider = str(provider_name or "").strip()
    if not normalized_name:
        raise ValueError("Pool name must not be empty")
    if not normalized_provider:
        raise ValueError("Provider name must not be empty")
    existing = await db.execute(
        select(TrunkPoolRow).where(
            TrunkPoolRow.provider_name == normalized_provider,
            TrunkPoolRow.name == normalized_name,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError("Trunk pool already exists for that provider")
    pool = TrunkPoolRow(
        trunk_pool_id=_pool_id(),
        provider_name=normalized_provider,
        name=normalized_name,
        selection_policy="first_available",
        is_active=True,
    )
    db.add(pool)
    await db.flush()
    await write_audit_event(
        db,
        tenant_id=actor_tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="admin.sip.pool.create",
        resource_type="sip_trunk_pool",
        resource_id=pool.trunk_pool_id,
        detail={"name": pool.name, "provider_name": pool.provider_name},
    )
    return await get_admin_sip_pool_record(db, pool.trunk_pool_id)


async def update_admin_sip_pool(
    db: AsyncSession,
    *,
    trunk_pool_id: str,
    name: str | None,
    is_active: bool | None,
    actor_id: str,
    actor_tenant_id: str,
) -> AdminTrunkPoolRecord:
    pool = await db.get(TrunkPoolRow, trunk_pool_id)
    if pool is None:
        raise LookupError("Trunk pool not found")
    if name is not None:
        candidate = str(name).strip()
        if not candidate:
            raise ValueError("Pool name must not be empty")
        pool.name = candidate
    if is_active is not None:
        pool.is_active = is_active
    await write_audit_event(
        db,
        tenant_id=actor_tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="admin.sip.pool.update",
        resource_type="sip_trunk_pool",
        resource_id=pool.trunk_pool_id,
        detail={"name": pool.name, "is_active": pool.is_active},
    )
    return await get_admin_sip_pool_record(db, pool.trunk_pool_id)


async def add_admin_sip_pool_member(
    db: AsyncSession,
    *,
    trunk_pool_id: str,
    trunk_id: str,
    priority: int,
    actor_id: str,
    actor_tenant_id: str,
) -> AdminTrunkPoolRecord:
    pool = await db.get(TrunkPoolRow, trunk_pool_id)
    if pool is None:
        raise LookupError("Trunk pool not found")
    trunk = await db.get(SIPTrunkRow, trunk_id)
    if trunk is None:
        raise LookupError("SIP trunk not found")
    if (trunk.provider_name or "") != pool.provider_name:
        raise ValueError("Trunk provider does not match pool provider")
    existing = await db.execute(
        select(TrunkPoolMemberRow).where(
            TrunkPoolMemberRow.trunk_pool_id == trunk_pool_id,
            TrunkPoolMemberRow.trunk_id == trunk_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError("Trunk is already a member of this pool")
    db.add(
        TrunkPoolMemberRow(
            trunk_pool_member_id=_member_id(),
            trunk_pool_id=trunk_pool_id,
            trunk_id=trunk_id,
            priority=priority,
            is_active=True,
        )
    )
    await db.flush()
    await write_audit_event(
        db,
        tenant_id=actor_tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="admin.sip.pool.member.add",
        resource_type="sip_trunk_pool",
        resource_id=pool.trunk_pool_id,
        detail={"trunk_id": trunk_id, "priority": priority},
    )
    return await get_admin_sip_pool_record(db, trunk_pool_id)


async def remove_admin_sip_pool_member(
    db: AsyncSession,
    *,
    trunk_pool_id: str,
    trunk_id: str,
    actor_id: str,
    actor_tenant_id: str,
) -> AdminTrunkPoolRecord:
    pool = await db.get(TrunkPoolRow, trunk_pool_id)
    if pool is None:
        raise LookupError("Trunk pool not found")
    result = await db.execute(
        select(TrunkPoolMemberRow).where(
            TrunkPoolMemberRow.trunk_pool_id == trunk_pool_id,
            TrunkPoolMemberRow.trunk_id == trunk_id,
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise LookupError("Trunk pool member not found")
    await db.delete(member)
    await db.flush()
    await write_audit_event(
        db,
        tenant_id=actor_tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="admin.sip.pool.member.remove",
        resource_type="sip_trunk_pool",
        resource_id=pool.trunk_pool_id,
        detail={"trunk_id": trunk_id},
    )
    return await get_admin_sip_pool_record(db, trunk_pool_id)


async def assign_admin_sip_pool_to_tenant(
    db: AsyncSession,
    *,
    trunk_pool_id: str,
    tenant_id: str,
    tenant_label: str | None,
    is_default: bool,
    max_channels: int | None,
    reserved_channels: int | None,
    actor_id: str,
    actor_tenant_id: str,
) -> AdminTrunkPoolRecord:
    pool = await db.get(TrunkPoolRow, trunk_pool_id)
    if pool is None:
        raise LookupError("Trunk pool not found")
    tenant = await db.get(TenantRow, tenant_id)
    if tenant is None:
        raise LookupError("Tenant not found")
    label = str(tenant_label or "").strip() or pool.name
    normalized_max_channels, normalized_reserved_channels = _normalized_assignment_quota(
        max_channels=max_channels,
        reserved_channels=reserved_channels,
    )
    existing = await db.execute(
        select(TenantTrunkPoolRow).where(
            TenantTrunkPoolRow.tenant_id == tenant_id,
            TenantTrunkPoolRow.trunk_pool_id == trunk_pool_id,
        )
    )
    row = existing.scalar_one_or_none()
    if is_default:
        other_defaults = await db.execute(
            select(TenantTrunkPoolRow).where(
                TenantTrunkPoolRow.tenant_id == tenant_id,
                TenantTrunkPoolRow.trunk_pool_id != trunk_pool_id,
            )
        )
        for other in other_defaults.scalars().all():
            other.is_default = False
    if row is None:
        row = TenantTrunkPoolRow(
            tenant_trunk_pool_id=_assignment_id(),
            tenant_id=tenant_id,
            trunk_pool_id=trunk_pool_id,
            tenant_label=label,
            is_default=is_default,
            is_active=True,
            max_channels=normalized_max_channels,
            reserved_channels=normalized_reserved_channels,
        )
        db.add(row)
    else:
        row.tenant_label = label
        row.is_default = is_default
        row.is_active = True
        if normalized_max_channels is not None:
            row.max_channels = normalized_max_channels
        if normalized_reserved_channels is not None:
            row.reserved_channels = normalized_reserved_channels
    await db.flush()
    await write_audit_event(
        db,
        tenant_id=actor_tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="admin.sip.pool.assign",
        resource_type="sip_trunk_pool",
        resource_id=trunk_pool_id,
        detail={
            "tenant_id": tenant_id,
            "tenant_label": label,
            "is_default": is_default,
            "max_channels": normalized_max_channels,
            "reserved_channels": normalized_reserved_channels,
        },
    )
    return await get_admin_sip_pool_record(db, trunk_pool_id)


async def update_admin_sip_pool_assignment(
    db: AsyncSession,
    *,
    trunk_pool_id: str,
    tenant_id: str,
    tenant_label: str | None,
    is_default: bool | None,
    is_active: bool | None,
    max_channels: int | None,
    reserved_channels: int | None,
    set_tenant_label: bool,
    set_is_default: bool,
    set_is_active: bool,
    set_max_channels: bool,
    set_reserved_channels: bool,
    actor_id: str,
    actor_tenant_id: str,
) -> AdminTrunkPoolRecord:
    pool = await db.get(TrunkPoolRow, trunk_pool_id)
    if pool is None:
        raise LookupError("Trunk pool not found")
    result = await db.execute(
        select(TenantTrunkPoolRow).where(
            TenantTrunkPoolRow.tenant_id == tenant_id,
            TenantTrunkPoolRow.trunk_pool_id == trunk_pool_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise LookupError("Tenant trunk pool assignment not found")

    next_max_channels = max_channels if set_max_channels else row.max_channels
    next_reserved_channels = reserved_channels if set_reserved_channels else row.reserved_channels
    normalized_max_channels, normalized_reserved_channels = _normalized_assignment_quota(
        max_channels=next_max_channels,
        reserved_channels=next_reserved_channels,
    )

    if set_tenant_label:
        candidate = str(tenant_label or "").strip()
        row.tenant_label = candidate or pool.name
    if set_is_default and is_default is not None:
        if is_default:
            other_defaults = await db.execute(
                select(TenantTrunkPoolRow).where(
                    TenantTrunkPoolRow.tenant_id == tenant_id,
                    TenantTrunkPoolRow.trunk_pool_id != trunk_pool_id,
                )
            )
            for other in other_defaults.scalars().all():
                other.is_default = False
        row.is_default = is_default
    if set_is_active and is_active is not None:
        row.is_active = is_active
    if set_max_channels:
        row.max_channels = normalized_max_channels
    if set_reserved_channels:
        row.reserved_channels = normalized_reserved_channels

    await db.flush()
    await write_audit_event(
        db,
        tenant_id=actor_tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="admin.sip.pool.assignment.update",
        resource_type="sip_trunk_pool",
        resource_id=trunk_pool_id,
        detail={
            "tenant_id": tenant_id,
            "tenant_label": row.tenant_label,
            "is_default": row.is_default,
            "is_active": row.is_active,
            "max_channels": row.max_channels,
            "reserved_channels": row.reserved_channels,
        },
    )
    return await get_admin_sip_pool_record(db, trunk_pool_id)


async def revoke_admin_sip_pool_assignment(
    db: AsyncSession,
    *,
    trunk_pool_id: str,
    tenant_id: str,
    actor_id: str,
    actor_tenant_id: str,
) -> AdminTrunkPoolRecord:
    pool = await db.get(TrunkPoolRow, trunk_pool_id)
    if pool is None:
        raise LookupError("Trunk pool not found")
    result = await db.execute(
        select(TenantTrunkPoolRow).where(
            TenantTrunkPoolRow.tenant_id == tenant_id,
            TenantTrunkPoolRow.trunk_pool_id == trunk_pool_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise LookupError("Tenant trunk pool assignment not found")
    await db.delete(assignment)
    await db.flush()
    await write_audit_event(
        db,
        tenant_id=actor_tenant_id,
        actor_id=actor_id,
        actor_type="user",
        action="admin.sip.pool.revoke",
        resource_type="sip_trunk_pool",
        resource_id=trunk_pool_id,
        detail={"tenant_id": tenant_id},
    )
    return await get_admin_sip_pool_record(db, trunk_pool_id)
