"use client";

import { useMemo, useState } from "react";
import { AccessPanel } from "@/components/auth/access-panel";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { TableState } from "@/components/ui/table-state";
import { useAdminAudit } from "@/lib/api";
import { useDashboardAccess } from "@/lib/current-user";

export default function AdminAuditPage() {
  const { roleResolved, canAccessAdminAudit, canAccessAdminTenants } = useDashboardAccess();
  const [tenantId, setTenantId] = useState("");
  const [actorId, setActorId] = useState("");
  const [action, setAction] = useState("");
  const [resourceType, setResourceType] = useState("");
  const [submitted, setSubmitted] = useState({
    tenantId: "",
    actorId: "",
    action: "",
    resourceType: "",
  });
  const params = useMemo(
    () => ({
      tenantId: submitted.tenantId,
      actorId: submitted.actorId,
      action: submitted.action,
      resourceType: submitted.resourceType,
    }),
    [submitted]
  );
  const { data, error } = useAdminAudit(params, canAccessAdminAudit);

  if (!roleResolved) {
    return (
      <Card>
        <CardBody>
          <p className="text-sm text-text-muted">Loading admin capabilities…</p>
        </CardBody>
      </Card>
    );
  }

  if (!canAccessAdminAudit) {
    return (
      <AccessPanel
        title="Admin Audit"
        message="Control-plane audit access is restricted to admin role or above."
      />
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-text-primary">Admin Audit</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Scoped audit search across user admin, tenant admin, SIP, and system operations.
        </p>
      </div>

      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-text-primary">Filters</h2>
        </CardHeader>
        <CardBody className="grid gap-3 md:grid-cols-5">
          {canAccessAdminTenants ? (
            <input
              value={tenantId}
              onChange={(event) => setTenantId(event.target.value)}
              placeholder="tenant_id"
              className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
            />
          ) : null}
          <input
            value={actorId}
            onChange={(event) => setActorId(event.target.value)}
            placeholder="actor_id"
            className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
          />
          <input
            value={action}
            onChange={(event) => setAction(event.target.value)}
            placeholder="action"
            className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
          />
          <input
            value={resourceType}
            onChange={(event) => setResourceType(event.target.value)}
            placeholder="resource_type"
            className="rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary"
          />
          <Button
            onClick={() => setSubmitted({ tenantId, actorId, action, resourceType })}
          >
            Apply Filters
          </Button>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <span className="text-sm font-medium text-text-secondary">
            {data?.total ?? 0} audit events
          </span>
        </CardHeader>
        <CardBody className="p-0">
          {error ? (
            <TableState kind="error" title="Failed to load audit events" message={error.message} columns={6} />
          ) : !data ? (
            <TableState kind="loading" message="Loading audit events…" columns={6} rows={6} />
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-text-muted">
                  <th className="px-5 py-3 font-medium">Action</th>
                  <th className="px-5 py-3 font-medium">Tenant</th>
                  <th className="px-5 py-3 font-medium">Actor</th>
                  <th className="px-5 py-3 font-medium">Resource</th>
                  <th className="px-5 py-3 font-medium">Created</th>
                  <th className="px-5 py-3 font-medium">Detail</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((event) => (
                  <tr key={event.event_id} className="border-b border-border last:border-0">
                    <td className="px-5 py-3 text-text-primary">{event.action}</td>
                    <td className="px-5 py-3 font-mono text-xs text-text-muted">{event.tenant_id}</td>
                    <td className="px-5 py-3">
                      <div className="text-text-secondary">{event.actor_id}</div>
                      <div className="text-[11px] text-text-muted">{event.actor_type}</div>
                    </td>
                    <td className="px-5 py-3">
                      <div className="text-text-secondary">{event.resource_type}</div>
                      <div className="font-mono text-[11px] text-text-muted">{event.resource_id}</div>
                    </td>
                    <td className="px-5 py-3 text-xs text-text-muted">
                      {new Date(event.created_at).toLocaleString()}
                    </td>
                    <td className="px-5 py-3">
                      <pre className="max-w-[380px] overflow-x-auto whitespace-pre-wrap text-[11px] text-text-muted">
                        {JSON.stringify(event.detail, null, 2)}
                      </pre>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
