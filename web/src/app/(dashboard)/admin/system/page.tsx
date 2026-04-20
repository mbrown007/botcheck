"use client";

import { useEffect, useState } from "react";
import { AccessPanel } from "@/components/auth/access-panel";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/badge";
import { TableState } from "@/components/ui/table-state";
import { patchAdminSystemQuotas, useAdminSystemConfig, useAdminSystemHealth, useAdminSystemQuotas } from "@/lib/api";
import { useDashboardAccess } from "@/lib/current-user";

export default function AdminSystemPage() {
  const { roleResolved, canAccessAdminSystem } = useDashboardAccess();
  const { data: health, error: healthError } = useAdminSystemHealth(canAccessAdminSystem);
  const { data: config, error: configError } = useAdminSystemConfig(canAccessAdminSystem);
  const { data: quotas, error: quotaError, mutate: mutateQuotas } = useAdminSystemQuotas(canAccessAdminSystem);
  const [quotaValues, setQuotaValues] = useState<Record<string, string>>({});
  const [savingQuotas, setSavingQuotas] = useState(false);
  const [message, setMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    if (!quotas) {
      return;
    }
    setQuotaValues(
      Object.fromEntries(
        Object.entries(quotas.quota_defaults).map(([key, value]) => [key, String(value)])
      )
    );
  }, [quotas]);

  if (!roleResolved) {
    return (
      <Card>
        <CardBody>
          <p className="text-sm text-text-muted">Loading admin capabilities…</p>
        </CardBody>
      </Card>
    );
  }

  if (!canAccessAdminSystem) {
    return (
      <AccessPanel
        title="System Admin"
        message="Platform system controls are restricted to system_admin."
      />
    );
  }

  async function handleSaveQuotas() {
    setSavingQuotas(true);
    setMessage("");
    setErrorMessage("");
    try {
      await patchAdminSystemQuotas({
        quota_defaults: Object.fromEntries(
          Object.entries(quotaValues).map(([key, value]) => [key, Number(value)])
        ),
      });
      setMessage("Platform quota defaults updated.");
      await mutateQuotas();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to update quota defaults");
    } finally {
      setSavingQuotas(false);
    }
  }

  const configEntries = Object.entries(config?.config ?? {}).sort(([left], [right]) =>
    left.localeCompare(right)
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-text-primary">System Admin</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Platform health, default quotas, and redacted runtime config.
        </p>
      </div>

      {message ? <p className="text-sm text-pass">{message}</p> : null}
      {errorMessage ? <p className="text-sm text-fail">{errorMessage}</p> : null}

      <Card>
        <CardHeader>
          <span className="text-xs uppercase tracking-[0.16em] text-text-muted">Platform Health</span>
        </CardHeader>
        <CardBody>
          {healthError ? (
            <p className="text-sm text-fail">{healthError.message}</p>
          ) : !health ? (
            <p className="text-sm text-text-muted">Loading system health…</p>
          ) : (
            <div className="flex flex-wrap gap-6">
              {/* Infrastructure */}
              <div className="flex items-center gap-3">
                {[
                  { label: "Database", value: health.database.status === "ok" ? "pass" : "fail", status: health.database.status },
                  { label: "Redis", value: health.redis.status === "ok" ? "pass" : "warn", status: health.redis.status },
                  { label: "LiveKit", value: health.livekit.status === "configured" ? "pass" : "warn", status: health.livekit.status },
                ].map(({ label, value, status }) => (
                  <div key={label} className="flex items-center gap-1.5 rounded-lg border border-border bg-bg-elevated px-3 py-1.5">
                    <span className="text-xs font-medium text-text-secondary">{label}</span>
                    <StatusBadge value={value as "pass" | "fail" | "warn"} label={status} />
                  </div>
                ))}
              </div>
              {/* Providers */}
              <div className="flex flex-wrap items-center gap-2">
                {Object.entries(health.providers).map(([provider, state]) => {
                  const isAgentSide = state.key_location === "agent";
                  const badgeValue = state.configured ? "pass" : isAgentSide ? "info" : "warn";
                  const badgeLabel = state.configured ? "ok" : isAgentSide ? "agent" : "missing";
                  return (
                    <div key={provider} className="flex items-center gap-1.5 rounded-lg border border-border bg-bg-elevated px-3 py-1.5">
                      <span className="text-xs font-medium text-text-secondary">{provider}</span>
                      <StatusBadge value={badgeValue as "pass" | "info" | "warn"} label={badgeLabel} />
                      <span className="text-[11px] text-text-muted">via {state.key_location}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-text-primary">Platform Quota Defaults</h2>
        </CardHeader>
        <CardBody>
          {quotaError ? (
            <p className="text-sm text-fail">{quotaError.message}</p>
          ) : !quotas ? (
            <TableState kind="loading" message="Loading quota defaults…" columns={4} rows={3} />
          ) : (
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3">
                {Object.entries(quotaValues).map(([key, value]) => (
                  <label key={key} className="block">
                    <span className="mb-1.5 block text-xs text-text-secondary">{key}</span>
                    <input
                      value={value}
                      onChange={(event) =>
                        setQuotaValues((current) => ({ ...current, [key]: event.target.value }))
                      }
                      className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
                    />
                  </label>
                ))}
              </div>
              <Button onClick={() => void handleSaveQuotas()} disabled={savingQuotas}>
                {savingQuotas ? "Saving…" : "Save Quota Defaults"}
              </Button>
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-text-primary">Effective Config</h2>
        </CardHeader>
        <CardBody>
          {configError ? (
            <p className="text-sm text-fail">{configError.message}</p>
          ) : !config ? (
            <p className="text-sm text-text-muted">Loading config…</p>
          ) : (
            <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
              {configEntries.map(([key, value]) => (
                <div key={key} className="rounded-md border border-border bg-bg-elevated px-3 py-2">
                  <div className="text-[11px] uppercase tracking-wide text-text-muted">{key}</div>
                  <div className="mt-1 break-all text-sm text-text-primary">{String(value)}</div>
                </div>
              ))}
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
