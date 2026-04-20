from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import UserContext, get_tenant_row, require_viewer, tenant_display_name
from ..config import settings
from ..database import get_db

router = APIRouter()


class TenantResponse(BaseModel):
    tenant_id: str
    name: str
    plan: str
    tier: str  # compatibility alias
    instance_timezone: str
    default_retention_profile: str
    redaction_enabled: bool
    tenant_context_locked: bool
    tenant_switcher_enabled: bool


@router.get("/me", response_model=TenantResponse)
async def get_current_tenant(
    user: UserContext = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    role = user.role.strip().lower()
    switcher_allowed = role in settings.tenant_switcher_allowed_roles
    tenant_switcher_enabled = settings.shared_instance_mode and switcher_allowed
    tenant_context_locked = not settings.shared_instance_mode
    tenant = await get_tenant_row(db, tenant_id=user.tenant_id)
    return TenantResponse(
        tenant_id=user.tenant_id,
        name=tenant_display_name(tenant, tenant_id=user.tenant_id),
        plan=settings.tenant_plan,
        tier=settings.tenant_plan,
        instance_timezone=settings.instance_timezone,
        default_retention_profile=settings.default_retention_profile,
        redaction_enabled=settings.redaction_enabled,
        tenant_context_locked=tenant_context_locked,
        tenant_switcher_enabled=tenant_switcher_enabled,
    )
