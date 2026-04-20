"use client";

import { useState } from "react";
import { AccessPanel } from "@/components/auth/access-panel";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/badge";
import { TableState } from "@/components/ui/table-state";
import {
  createAdminUser,
  lockAdminUser,
  resetAdminUser2FA,
  resetAdminUserPassword,
  revokeAdminUserSessions,
  unlockAdminUser,
  useAdminUsers,
} from "@/lib/api";
import { useDashboardAccess } from "@/lib/current-user";

const MANAGED_ROLES = ["viewer", "operator", "editor", "admin"] as const;

export default function AdminUsersPage() {
  const { roleResolved, canAccessAdminUsers } = useDashboardAccess();
  const { data, error, mutate } = useAdminUsers();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<(typeof MANAGED_ROLES)[number]>("viewer");
  const [creating, setCreating] = useState(false);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [message, setMessage] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string>("");

  if (!roleResolved) {
    return (
      <Card>
        <CardBody>
          <p className="text-sm text-text-muted">Loading admin capabilities…</p>
        </CardBody>
      </Card>
    );
  }

  if (!canAccessAdminUsers) {
    return (
      <AccessPanel
        title="User Admin"
        message="User administration is restricted to admin role or above."
      />
    );
  }

  async function handleCreate() {
    setCreating(true);
    setMessage("");
    setErrorMessage("");
    try {
      await createAdminUser({ email, password, role, is_active: true });
      setEmail("");
      setPassword("");
      setRole("viewer");
      setMessage("User created.");
      await mutate();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to create user");
    } finally {
      setCreating(false);
    }
  }

  async function runAction(key: string, action: () => Promise<unknown>, success: string) {
    setBusyKey(key);
    setMessage("");
    setErrorMessage("");
    try {
      await action();
      setMessage(success);
      await mutate();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Admin action failed");
    } finally {
      setBusyKey(null);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-text-primary">User Admin</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Tenant-scoped user lifecycle, sessions, and recovery actions.
        </p>
      </div>

      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-text-primary">Create User</h2>
        </CardHeader>
        <CardBody className="grid gap-3 md:grid-cols-4">
          <input
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="user@example.com"
            className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
          />
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Temporary password"
            type="password"
            className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
          />
          <select
            value={role}
            onChange={(event) => setRole(event.target.value as (typeof MANAGED_ROLES)[number])}
            className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
          >
            {MANAGED_ROLES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
          <Button
            onClick={() => void handleCreate()}
            disabled={creating || !email.trim() || password.trim().length < 8}
          >
            {creating ? "Creating…" : "Create User"}
          </Button>
        </CardBody>
      </Card>

      {message ? <p className="text-sm text-pass">{message}</p> : null}
      {errorMessage ? <p className="text-sm text-fail">{errorMessage}</p> : null}

      <Card>
        <CardHeader>
          <span className="text-sm font-medium text-text-secondary">
            {data?.total ?? 0} users
          </span>
        </CardHeader>
        <CardBody className="p-0">
          {error ? (
            <TableState kind="error" title="Failed to load users" message={error.message} columns={7} />
          ) : !data ? (
            <TableState kind="loading" message="Loading users…" columns={7} rows={5} />
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-text-muted">
                  <th className="px-5 py-3 font-medium">Email</th>
                  <th className="px-5 py-3 font-medium">Role</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium">2FA</th>
                  <th className="px-5 py-3 font-medium">Sessions</th>
                  <th className="px-5 py-3 font-medium hidden lg:table-cell">Last Login</th>
                  <th className="px-5 py-3 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((user) => {
                  const locked = Boolean(user.locked_until) || !user.is_active;
                  return (
                    <tr key={user.user_id} className="border-b border-border last:border-0">
                      <td className="px-5 py-3">
                        <div className="text-text-primary">{user.email}</div>
                        <div className="font-mono text-[11px] text-text-muted">{user.user_id}</div>
                      </td>
                      <td className="px-5 py-3">{user.role}</td>
                      <td className="px-5 py-3">
                        <StatusBadge
                          value={locked ? "warn" : "pass"}
                          label={locked ? "locked" : "active"}
                        />
                      </td>
                      <td className="px-5 py-3">
                        <StatusBadge
                          value={user.totp_enabled ? "pass" : "pending"}
                          label={user.totp_enabled ? "enabled" : "not enrolled"}
                        />
                      </td>
                      <td className="px-5 py-3 font-mono text-text-secondary">
                        {user.active_session_count}
                      </td>
                      <td className="hidden px-5 py-3 text-xs text-text-muted lg:table-cell">
                        {user.last_login_at ? new Date(user.last_login_at).toLocaleString() : "—"}
                      </td>
                      <td className="px-5 py-3">
                        <div className="flex flex-wrap justify-end gap-2">
                          {user.is_active ? (
                            <Button
                              size="sm"
                              variant="secondary"
                              disabled={busyKey === `${user.user_id}:lock`}
                              onClick={() =>
                                void runAction(
                                  `${user.user_id}:lock`,
                                  () => lockAdminUser(user.user_id),
                                  "User locked and sessions revoked."
                                )
                              }
                            >
                              Lock
                            </Button>
                          ) : (
                            <Button
                              size="sm"
                              variant="secondary"
                              disabled={busyKey === `${user.user_id}:unlock`}
                              onClick={() =>
                                void runAction(
                                  `${user.user_id}:unlock`,
                                  () => unlockAdminUser(user.user_id),
                                  "User unlocked."
                                )
                              }
                            >
                              Unlock
                            </Button>
                          )}
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={busyKey === `${user.user_id}:sessions`}
                            onClick={() =>
                              void runAction(
                                `${user.user_id}:sessions`,
                                () => revokeAdminUserSessions(user.user_id),
                                "Sessions revoked."
                              )
                            }
                          >
                            Revoke Sessions
                          </Button>
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={busyKey === `${user.user_id}:2fa`}
                            onClick={() =>
                              void runAction(
                                `${user.user_id}:2fa`,
                                () => resetAdminUser2FA(user.user_id),
                                "2FA reset."
                              )
                            }
                          >
                            Reset 2FA
                          </Button>
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={busyKey === `${user.user_id}:password`}
                            onClick={() => {
                              const nextPassword = window.prompt(
                                `Set a new password for ${user.email}`,
                                ""
                              );
                              if (!nextPassword || nextPassword.trim().length < 8) {
                                return;
                              }
                              void runAction(
                                `${user.user_id}:password`,
                                () =>
                                  resetAdminUserPassword(user.user_id, {
                                    password: nextPassword.trim(),
                                  }),
                                "Password reset and sessions revoked."
                              );
                            }}
                          >
                            Reset Password
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
