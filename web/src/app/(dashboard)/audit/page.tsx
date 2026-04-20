"use client";

import { useMemo, useState } from "react";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { TableState } from "@/components/ui/table-state";
import { useAuditEvents } from "@/lib/api";

function toIso(value: string): string | undefined {
  if (!value) {
    return undefined;
  }
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) {
    return undefined;
  }
  return d.toISOString();
}

function shortDetail(detail: Record<string, unknown>): string {
  const text = JSON.stringify(detail);
  if (text.length <= 120) {
    return text;
  }
  return `${text.slice(0, 117)}...`;
}

export default function AuditPage() {
  const [action, setAction] = useState("");
  const [resourceType, setResourceType] = useState("");
  const [actorId, setActorId] = useState("");
  const [fromLocal, setFromLocal] = useState("");
  const [toLocal, setToLocal] = useState("");
  const [limit, setLimit] = useState("200");

  const filters = useMemo(
    () => ({
      action: action || undefined,
      resourceType: resourceType || undefined,
      actorId: actorId || undefined,
      fromTs: toIso(fromLocal),
      toTs: toIso(toLocal),
      limit: Number(limit) > 0 ? Number(limit) : 200,
    }),
    [action, actorId, fromLocal, limit, resourceType, toLocal]
  );

  const { data: events, error } = useAuditEvents(filters);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-text-primary">Security & Audit</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Immutable audit timeline for scenario and run lifecycle actions.
        </p>
      </div>

      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-text-primary">Filters</h2>
        </CardHeader>
        <CardBody className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            <label className="block">
              <span className="mb-1.5 block text-xs text-text-secondary">Action</span>
              <input
                value={action}
                onChange={(e) => setAction(e.target.value)}
                placeholder="run.create"
                className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-xs text-text-secondary">Resource Type</span>
              <select
                value={resourceType}
                onChange={(e) => setResourceType(e.target.value)}
                className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
              >
                <option value="">All</option>
                <option value="run">run</option>
                <option value="scenario">scenario</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-1.5 block text-xs text-text-secondary">Actor ID</span>
              <input
                value={actorId}
                onChange={(e) => setActorId(e.target.value)}
                placeholder="harness"
                className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
              />
            </label>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <label className="block">
              <span className="mb-1.5 block text-xs text-text-secondary">From</span>
              <input
                type="datetime-local"
                value={fromLocal}
                onChange={(e) => setFromLocal(e.target.value)}
                className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-xs text-text-secondary">To</span>
              <input
                type="datetime-local"
                value={toLocal}
                onChange={(e) => setToLocal(e.target.value)}
                className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-xs text-text-secondary">Limit</span>
              <input
                value={limit}
                onChange={(e) => setLimit(e.target.value)}
                className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
              />
            </label>
          </div>

          <div className="flex justify-end">
            <Button
              variant="secondary"
              onClick={() => {
                setAction("");
                setResourceType("");
                setActorId("");
                setFromLocal("");
                setToLocal("");
                setLimit("200");
              }}
            >
              Clear Filters
            </Button>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <span className="text-sm font-medium text-text-secondary">
            {events?.length ?? 0} events
          </span>
        </CardHeader>
        <CardBody className="p-0">
          {error && (
            <TableState
              kind="error"
              title="Failed to load audit log"
              message={error.message}
              columns={5}
            />
          )}
          {!events && !error && (
            <TableState kind="loading" message="Loading audit events…" columns={5} rows={6} />
          )}
          {events?.length === 0 && (
            <TableState
              kind="empty"
              title="No matching audit events"
              message="Try broadening the filters or adjusting the time window."
              columns={5}
            />
          )}
          {events && events.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-text-muted">
                  <th className="px-5 py-3 font-medium">Time</th>
                  <th className="px-5 py-3 font-medium">Action</th>
                  <th className="px-5 py-3 font-medium">Actor</th>
                  <th className="px-5 py-3 font-medium">Resource</th>
                  <th className="px-5 py-3 font-medium hidden lg:table-cell">Detail</th>
                </tr>
              </thead>
              <tbody>
                {events.map((event) => (
                  <tr
                    key={event.event_id}
                    className="border-b border-border last:border-0 hover:bg-bg-elevated transition-colors"
                  >
                    <td className="px-5 py-3 text-xs text-text-muted">
                      {new Date(event.created_at).toLocaleString()}
                    </td>
                    <td className="px-5 py-3 text-text-primary">{event.action}</td>
                    <td className="px-5 py-3 font-mono text-xs text-text-secondary">
                      {event.actor_id}
                    </td>
                    <td className="px-5 py-3 text-text-secondary">
                      {event.resource_type}:{event.resource_id}
                    </td>
                    <td className="px-5 py-3 hidden lg:table-cell">
                      <span className="font-mono text-xs text-text-muted">
                        {shortDetail(event.detail)}
                      </span>
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
