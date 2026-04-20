import { normalizeRole, type AppRole } from "@/lib/rbac";

interface AuthSession {
  token: string;
  tenantId: string;
  tenantName: string;
  role?: AppRole;
  userId?: string;
  refreshToken?: string;
  refreshExpiresAt?: number;
}

const AUTH_SESSION_KEY = "botcheck_auth_session_v1";

export const DEV_LOGIN_TOKEN =
  process.env.NEXT_PUBLIC_DEV_USER_TOKEN ?? "";

interface JwtPayload {
  exp?: number;
}

interface AuthRefreshResponse {
  access_token?: string;
  refresh_token?: string;
  expires_in_s?: number;
  refresh_expires_in_s?: number;
  tenant_id?: string;
  tenant_name?: string;
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700";

let refreshInFlight: Promise<AuthSession | null> | null = null;

function decodeJwtPayload(token: string): JwtPayload | null {
  const parts = token.split(".");
  if (parts.length < 2) {
    return null;
  }
  const payloadPart = parts[1];
  try {
    const normalized = payloadPart.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
    const decoded = window.atob(padded);
    return JSON.parse(decoded) as JwtPayload;
  } catch {
    return null;
  }
}

export function getAuthSession(): AuthSession | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(AUTH_SESSION_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as Partial<AuthSession>;
    const refreshToken =
      typeof parsed.refreshToken === "string" && parsed.refreshToken
        ? parsed.refreshToken
        : undefined;
    const refreshExpiresAt =
      typeof parsed.refreshExpiresAt === "number" &&
      Number.isFinite(parsed.refreshExpiresAt)
        ? parsed.refreshExpiresAt
        : undefined;
    const role =
      typeof parsed.role === "string" && parsed.role ? normalizeRole(parsed.role) ?? undefined : undefined;
    const userId =
      typeof parsed.userId === "string" && parsed.userId ? parsed.userId : undefined;
    if (
      typeof parsed.token === "string" &&
      parsed.token &&
      typeof parsed.tenantId === "string" &&
      parsed.tenantId &&
      typeof parsed.tenantName === "string" &&
      parsed.tenantName
    ) {
      const payload = decodeJwtPayload(parsed.token);
      const nowS = Date.now() / 1000;
      const accessExpired = !payload?.exp || nowS >= payload.exp;
      const refreshValid =
        !!refreshToken &&
        typeof refreshExpiresAt === "number" &&
        nowS < refreshExpiresAt;
      if (accessExpired && !refreshValid) {
        clearAuthSession();
        return null;
      }
      return {
        token: parsed.token,
        tenantId: parsed.tenantId,
        tenantName: parsed.tenantName,
        role,
        userId,
        refreshToken,
        refreshExpiresAt,
      };
    }
  } catch {
    // Ignore malformed persisted sessions.
  }
  return null;
}

export function setAuthSession(session: AuthSession): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(session));
}

export function clearAuthSession(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(AUTH_SESSION_KEY);
}

function isAccessTokenExpiringSoon(token: string, skewS = 30): boolean {
  const payload = decodeJwtPayload(token);
  if (!payload?.exp) {
    return true;
  }
  return Date.now() / 1000 >= payload.exp - skewS;
}

async function refreshSessionToken(
  session: AuthSession
): Promise<AuthSession | null> {
  if (
    !session.refreshToken ||
    typeof session.refreshExpiresAt !== "number" ||
    Date.now() / 1000 >= session.refreshExpiresAt
  ) {
    clearAuthSession();
    return null;
  }

  const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: session.refreshToken }),
  });
  if (!res.ok) {
    clearAuthSession();
    return null;
  }
  const payload = (await res.json()) as AuthRefreshResponse;
  if (
    typeof payload.access_token !== "string" ||
    !payload.access_token ||
    typeof payload.refresh_token !== "string" ||
    !payload.refresh_token
  ) {
    clearAuthSession();
    return null;
  }

  const refreshed: AuthSession = {
    token: payload.access_token,
    tenantId:
      typeof payload.tenant_id === "string" && payload.tenant_id
        ? payload.tenant_id
        : session.tenantId,
    tenantName:
      typeof payload.tenant_name === "string" && payload.tenant_name
        ? payload.tenant_name
        : session.tenantName,
    role: session.role,
    userId: session.userId,
    refreshToken: payload.refresh_token,
    refreshExpiresAt:
      Math.floor(Date.now() / 1000) + (payload.refresh_expires_in_s ?? 0),
  };
  setAuthSession(refreshed);
  return refreshed;
}

export async function ensureFreshAuthSession(): Promise<AuthSession | null> {
  if (typeof window === "undefined") {
    return null;
  }
  const session = getAuthSession();
  if (!session) {
    return null;
  }
  if (!isAccessTokenExpiringSoon(session.token)) {
    return session;
  }
  if (refreshInFlight) {
    return refreshInFlight;
  }
  refreshInFlight = refreshSessionToken(session)
    .catch(() => {
      clearAuthSession();
      return null;
    })
    .finally(() => {
      refreshInFlight = null;
    });
  return refreshInFlight;
}
