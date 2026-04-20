"use client";

import { useEffect } from "react";
import { useCurrentUser } from "@/lib/api";
import { getAuthSession, setAuthSession } from "@/lib/auth";
import { getDashboardAccess, normalizeRole, type AppRole } from "@/lib/rbac";

function syncCurrentUserIntoSession(identity: {
  role: string;
  sub: string;
}): void {
  const session = getAuthSession();
  const role = normalizeRole(identity.role);
  if (!session || !role) {
    return;
  }
  if (session.role === role && session.userId === identity.sub) {
    return;
  }
  setAuthSession({
    ...session,
    role,
    userId: identity.sub,
  });
}

export function useCurrentRole(): AppRole | null {
  const { data, error } = useCurrentUser();
  const stored = getAuthSession()?.role ?? null;

  useEffect(() => {
    if (data?.role && data?.sub) {
      syncCurrentUserIntoSession({ role: data.role, sub: data.sub });
    }
  }, [data?.role, data?.sub]);

  const sessionRole = normalizeRole(stored);
  if (sessionRole) {
    return sessionRole;
  }
  if (error) {
    return null;
  }
  return normalizeRole(data?.role);
}

export function useDashboardAccess() {
  const { data, error } = useCurrentUser();
  const role = useCurrentRole();
  const roleResolved = Boolean(role) || Boolean(error) || Boolean(data?.role);
  return {
    role,
    roleResolved,
    ...getDashboardAccess(role),
  };
}
