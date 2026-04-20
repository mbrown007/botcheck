from __future__ import annotations

from typing import NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession

from .. import repo_runs
from ..exceptions import (
    ApiProblem,
    TRUNK_POOL_EMPTY,
    TRUNK_POOL_INACTIVE,
    TRUNK_POOL_NOT_FOUND,
    TRUNK_POOL_UNASSIGNED,
)
from ..models import SIPTrunkRow, TrunkPoolMemberRow, TrunkPoolRow


class ResolvedTrunkSelection(NamedTuple):
    trunk_id: str
    trunk_pool_id: str | None


async def resolve_sip_trunk_for_dispatch(
    db: AsyncSession,
    *,
    tenant_id: str,
    trunk_id: str | None,
    trunk_pool_id: str | None,
) -> ResolvedTrunkSelection:
    if trunk_pool_id is None:
        return ResolvedTrunkSelection(trunk_id=trunk_id or "", trunk_pool_id=None)

    pool = await repo_runs.get_trunk_pool_row(db, trunk_pool_id)
    if pool is None:
        raise ApiProblem(
            status=422,
            error_code=TRUNK_POOL_NOT_FOUND,
            detail="Configured trunk pool does not exist",
        )
    if not pool.is_active:
        raise ApiProblem(
            status=422,
            error_code=TRUNK_POOL_INACTIVE,
            detail="Configured trunk pool is inactive",
        )

    assignment = await repo_runs.get_active_tenant_trunk_pool_row(
        db,
        tenant_id=tenant_id,
        trunk_pool_id=trunk_pool_id,
    )
    if assignment is None:
        raise ApiProblem(
            status=422,
            error_code=TRUNK_POOL_UNASSIGNED,
            detail="Configured trunk pool is not assigned to this tenant",
        )

    members = await repo_runs.list_active_trunk_pool_members(db, trunk_pool_id)
    if not members:
        raise ApiProblem(
            status=422,
            error_code=TRUNK_POOL_EMPTY,
            detail="Configured trunk pool has no active trunks",
        )

    trunks_by_id = {
        trunk.trunk_id: trunk
        for trunk in await repo_runs.list_sip_trunks_for_ids(
            db,
            [member.trunk_id for member in members],
        )
        if trunk.is_active
    }
    selected = _select_pool_trunk(pool=pool, members=members, trunks_by_id=trunks_by_id)
    if selected is None:
        raise ApiProblem(
            status=422,
            error_code=TRUNK_POOL_EMPTY,
            detail="Configured trunk pool has no active trunks matching its provider",
        )

    return ResolvedTrunkSelection(trunk_id=selected.trunk_id, trunk_pool_id=trunk_pool_id)


def _select_pool_trunk(
    *,
    pool: TrunkPoolRow,
    members: list[TrunkPoolMemberRow],
    trunks_by_id: dict[str, SIPTrunkRow],
) -> SIPTrunkRow | None:
    for member in sorted(members, key=lambda row: (row.priority, row.trunk_id)):
        trunk = trunks_by_id.get(member.trunk_id)
        if trunk is None:
            continue
        if (trunk.provider_name or "") != pool.provider_name:
            continue
        return trunk
    return None
