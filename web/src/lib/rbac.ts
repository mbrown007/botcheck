const APP_ROLES = [
  "viewer",
  "operator",
  "editor",
  "admin",
  "system_admin",
] as const;

export type AppRole = (typeof APP_ROLES)[number];

const ROLE_RANK: Record<AppRole, number> = {
  viewer: 0,
  operator: 1,
  editor: 2,
  admin: 3,
  system_admin: 4,
};

export function normalizeRole(role: string | null | undefined): AppRole | null {
  if (!role) {
    return null;
  }
  return APP_ROLES.includes(role as AppRole) ? (role as AppRole) : null;
}

export function hasMinimumRole(
  role: string | null | undefined,
  minimum: AppRole
): boolean {
  const normalized = normalizeRole(role);
  if (!normalized) {
    return false;
  }
  return ROLE_RANK[normalized] >= ROLE_RANK[minimum];
}

export function isPlatformAdmin(role: string | null | undefined): boolean {
  return normalizeRole(role) === "system_admin";
}

export function getDashboardAccess(role: string | null | undefined) {
  return {
    canViewAdminSection: hasMinimumRole(role, "admin"),
    canViewGraiEvals: hasMinimumRole(role, "viewer"),
    canManageGraiSuites: hasMinimumRole(role, "editor"),
    canLaunchGraiRuns: hasMinimumRole(role, "operator"),
    canUsePlayground: hasMinimumRole(role, "editor"),
    canUseBuilder: hasMinimumRole(role, "editor"),
    canManageScenarios: hasMinimumRole(role, "editor"),
    canGenerateScenarios: hasMinimumRole(role, "admin"),
    canManageSchedules: hasMinimumRole(role, "editor"),
    canOperateRuns: hasMinimumRole(role, "operator"),
    canManagePacks: hasMinimumRole(role, "admin"),
    canManageAIScenarios: hasMinimumRole(role, "admin"),
    canManagePersonas: hasMinimumRole(role, "admin"),
    canManageTransportProfiles: hasMinimumRole(role, "editor"),
    canAccessAdminUsers: hasMinimumRole(role, "admin"),
    canAccessAdminAudit: hasMinimumRole(role, "admin"),
    canViewProviderQuota: hasMinimumRole(role, "operator"),
    canAccessAdminTenants: isPlatformAdmin(role),
    canAccessAdminProviders: isPlatformAdmin(role),
    canAccessAdminSip: isPlatformAdmin(role),
    canAccessAdminSystem: isPlatformAdmin(role),
  };
}
