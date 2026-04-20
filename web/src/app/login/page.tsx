"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { fetchCurrentUser, login, loginWithTotp, type TenantInfo } from "@/lib/api";
import { DEV_LOGIN_TOKEN, getAuthSession, setAuthSession } from "@/lib/auth";
import { normalizeRole } from "@/lib/rbac";

interface TenantOption {
  id: string;
  name: string;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700";

const DEFAULT_TENANT: TenantOption = { id: "default", name: "default" };

function mergeTenantOptions(
  current: TenantOption[],
  remote: TenantInfo | null
): TenantOption[] {
  const map = new Map<string, TenantOption>();
  map.set(DEFAULT_TENANT.id, DEFAULT_TENANT);
  for (const item of current) {
    map.set(item.id, item);
  }
  if (remote?.tenant_id) {
    map.set(remote.tenant_id, {
      id: remote.tenant_id,
      name: remote.name || remote.tenant_id,
    });
  }
  return Array.from(map.values());
}

export default function LoginPage() {
  const router = useRouter();
  const [tenants, setTenants] = useState<TenantOption[]>([DEFAULT_TENANT]);
  const [tenantId, setTenantId] = useState<string>(DEFAULT_TENANT.id);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [challengeToken, setChallengeToken] = useState<string | null>(null);
  const [error, setError] = useState<string>("");
  const [tenantLoadError, setTenantLoadError] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [tenantContextLocked, setTenantContextLocked] = useState(true);
  const [tenantSwitcherEnabled, setTenantSwitcherEnabled] = useState(false);

  const selectedTenant = tenants.find((item) => item.id === tenantId) ?? DEFAULT_TENANT;
  const showTenantSelector =
    !challengeToken && tenantSwitcherEnabled && !tenantContextLocked;

  useEffect(() => {
    const session = getAuthSession();
    if (session?.token) {
      router.replace("/scenarios" as Route);
    }
  }, [router]);

  useEffect(() => {
    let cancelled = false;

    async function loadTenantFromApi() {
      if (!DEV_LOGIN_TOKEN) {
        return;
      }
      try {
        const response = await fetch(`${API_BASE_URL}/tenants/me`, {
          headers: { Authorization: `Bearer ${DEV_LOGIN_TOKEN}` },
        });
        if (!response.ok) {
          throw new Error(`Tenant lookup failed (${response.status})`);
        }
        const tenant = (await response.json()) as TenantInfo;
        if (cancelled) {
          return;
        }
        setTenants((prev) => mergeTenantOptions(prev, tenant));
        setTenantId(tenant.tenant_id || DEFAULT_TENANT.id);
        setTenantContextLocked(tenant.tenant_context_locked ?? true);
        setTenantSwitcherEnabled(tenant.tenant_switcher_enabled ?? false);
      } catch {
        if (!cancelled) {
          setTenantLoadError("Tenant name unavailable until API lookup completes.");
          setTenantContextLocked(true);
          setTenantSwitcherEnabled(false);
        }
      }
    }

    void loadTenantFromApi();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    setSubmitting(true);
    try {
      let result;
      if (challengeToken) {
        if (!totpCode.trim()) {
          setError("Verification code is required.");
          return;
        }
        result = await loginWithTotp({
          challenge_token: challengeToken,
          code: totpCode.trim(),
        });
      } else {
        const normalisedEmail = email.trim().toLowerCase();
        if (!normalisedEmail) {
          setError("Email is required.");
          return;
        }
        if (!password) {
          setError("Password is required.");
          return;
        }
        if (showTenantSelector && !selectedTenant) {
          setError("Please select a valid tenant.");
          return;
        }
        result = await login({
          email: normalisedEmail,
          password,
          tenant_id: showTenantSelector ? selectedTenant.id : tenantId,
        });
      }

      if (result.requires_totp) {
        if (!result.challenge_token) {
          setError("TOTP challenge failed to initialize.");
          return;
        }
        setChallengeToken(result.challenge_token);
        setTotpCode("");
        return;
      }

      if (!result.access_token) {
        setError("Login failed: missing access token.");
        return;
      }
      if (!result.refresh_token || !result.refresh_expires_in_s) {
        setError("Login failed: missing refresh session token.");
        return;
      }

      setAuthSession({
        token: result.access_token,
        tenantId: result.tenant_id,
        tenantName: result.tenant_name,
        refreshToken: result.refresh_token,
        refreshExpiresAt:
          Math.floor(Date.now() / 1000) + result.refresh_expires_in_s,
      });
      try {
        const currentUser = await fetchCurrentUser(result.access_token);
        setAuthSession({
          token: result.access_token,
          tenantId: result.tenant_id,
          tenantName: result.tenant_name,
          role: normalizeRole(currentUser.role) ?? undefined,
          userId: currentUser.sub,
          refreshToken: result.refresh_token,
          refreshExpiresAt:
            Math.floor(Date.now() / 1000) + result.refresh_expires_in_s,
        });
      } catch {
        // Session is still valid; /auth/me will hydrate role metadata later.
      }
      router.push("/scenarios" as Route);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Login failed. Please try again.";
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-bg-base px-6 py-10 text-text-primary">
      <div className="mx-auto flex w-full max-w-md flex-col gap-6">
        <Link
          href={"/" as Route}
          className="text-xs font-mono uppercase tracking-wide text-text-muted hover:text-text-secondary"
        >
          ← Back to home
        </Link>
        <Card>
          <CardHeader>
            <div>
              <h1 className="text-lg font-semibold text-text-primary">Login</h1>
              <p className="mt-1 text-xs text-text-secondary">
                {tenantContextLocked
                  ? "Sign in to access your tenant workspace."
                  : "Select your tenant to access the BotCheck dashboard."}
              </p>
            </div>
          </CardHeader>
          <CardBody>
            <form className="space-y-4" onSubmit={handleSubmit}>
              {!challengeToken && (
                <>
                  <label className="block space-y-1">
                    <span className="text-xs font-medium uppercase tracking-wide text-text-muted">
                      Email
                    </span>
                    <input
                      type="email"
                      autoComplete="username"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      className="h-10 w-full rounded-md border border-border bg-bg-elevated px-3 text-sm text-text-primary outline-none focus:border-border-focus focus:ring-2 focus:ring-border-focus/40"
                      placeholder="admin@botcheck.local"
                    />
                  </label>

                  <label className="block space-y-1">
                    <span className="text-xs font-medium uppercase tracking-wide text-text-muted">
                      Password
                    </span>
                    <input
                      type="password"
                      autoComplete="current-password"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      className="h-10 w-full rounded-md border border-border bg-bg-elevated px-3 text-sm text-text-primary outline-none focus:border-border-focus focus:ring-2 focus:ring-border-focus/40"
                    />
                  </label>

                  {showTenantSelector ? (
                    <label className="block space-y-1">
                      <span className="text-xs font-medium uppercase tracking-wide text-text-muted">
                        Tenant
                      </span>
                      <select
                        value={tenantId}
                        onChange={(event) => setTenantId(event.target.value)}
                        className="h-10 w-full rounded-md border border-border bg-bg-elevated px-3 text-sm text-text-primary outline-none focus:border-border-focus focus:ring-2 focus:ring-border-focus/40"
                      >
                        {tenants.map((tenant) => (
                          <option key={tenant.id} value={tenant.id}>
                            {tenant.name}
                          </option>
                        ))}
                      </select>
                    </label>
                  ) : (
                    <div className="space-y-1 rounded-md border border-border bg-bg-elevated px-3 py-2">
                      <p className="text-xs font-medium uppercase tracking-wide text-text-muted">
                        Tenant
                      </p>
                      <p className="text-sm text-text-primary">{selectedTenant.name}</p>
                      <p className="text-[11px] text-text-muted">
                        Tenant context is locked for this deployment.
                      </p>
                    </div>
                  )}
                </>
              )}

              {challengeToken && (
                <label className="block space-y-1">
                  <span className="text-xs font-medium uppercase tracking-wide text-text-muted">
                    Verification Or Recovery Code
                  </span>
                  <input
                    type="text"
                    inputMode="text"
                    autoComplete="one-time-code"
                    value={totpCode}
                    onChange={(event) => setTotpCode(event.target.value)}
                    className="h-10 w-full rounded-md border border-border bg-bg-elevated px-3 text-sm text-text-primary outline-none focus:border-border-focus focus:ring-2 focus:ring-border-focus/40"
                    placeholder="123456 or ABCD-EFGH-IJKL"
                  />
                </label>
              )}

              {tenantLoadError && (
                <p className="text-xs text-text-muted">{tenantLoadError}</p>
              )}
              {!DEV_LOGIN_TOKEN && (
                <p className="text-xs text-text-muted">
                  Tenant metadata lookup uses API auth.
                </p>
              )}
              {challengeToken && (
                <p className="text-xs text-text-secondary">
                  Enter the 6-digit code from your authenticator app, or use a recovery code.
                </p>
              )}
              {error && <p className="text-xs text-fail">{error}</p>}

              <Button type="submit" className="w-full" disabled={submitting}>
                {submitting
                  ? "Signing in…"
                  : challengeToken
                    ? "Verify code"
                    : "Login"}
              </Button>
              {challengeToken && (
                <Button
                  type="button"
                  variant="secondary"
                  className="w-full"
                  onClick={() => {
                    setChallengeToken(null);
                    setTotpCode("");
                  }}
                >
                  Back
                </Button>
              )}
            </form>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
