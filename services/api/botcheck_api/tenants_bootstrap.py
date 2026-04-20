from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import TenantRow
from .auth import get_tenant_row


def _default_tenant_slug() -> str:
    candidate = re.sub(r"[^a-z0-9]+", "-", settings.tenant_id.strip().lower()).strip("-")
    return candidate or "default"


async def ensure_default_tenant(db: AsyncSession) -> TenantRow:
    existing = await get_tenant_row(db, tenant_id=settings.tenant_id)
    if existing is not None:
        return existing

    tenant = TenantRow(
        tenant_id=settings.tenant_id,
        slug=_default_tenant_slug(),
        display_name=settings.tenant_name,
        feature_overrides={},
        quota_config={},
    )
    db.add(tenant)
    await db.flush()
    return tenant
