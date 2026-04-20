"""Admin feature package."""

from fastapi import APIRouter

from .router_audit import router as audit_router
from .router_providers import router as providers_router
from .router_sip import router as sip_router
from .router_system import router as system_router
from .router_tenants import router as tenants_router
from .router_users import router as users_router

router = APIRouter()
router.include_router(users_router)
router.include_router(tenants_router)
router.include_router(audit_router)
router.include_router(providers_router)
router.include_router(sip_router)
router.include_router(system_router)

__all__ = ["router"]
