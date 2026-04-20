"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";

interface PackRunDetailHeaderProps {
  packRunId: string;
  packName?: string | null;
  createdAt?: string | null;
  failuresOnly: boolean;
  canCancel: boolean;
  canMarkFailed: boolean;
  actionLoading: "cancel" | "fail" | null;
  onToggleFailuresOnly: () => void;
  onCancel: () => void;
  onMarkFailed: () => void;
  formatTs: (value?: string | null) => string;
}

export function PackRunDetailHeader({
  packRunId,
  packName,
  createdAt,
  failuresOnly,
  canCancel,
  canMarkFailed,
  actionLoading,
  onToggleFailuresOnly,
  onCancel,
  onMarkFailed,
  formatTs,
}: PackRunDetailHeaderProps) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-text-primary">{packName || "Pack Run"}</h1>
        <p className="mt-0.5 font-mono text-sm text-text-secondary">{packRunId}</p>
        {createdAt ? (
          <p className="mt-0.5 text-xs text-text-muted">Created {formatTs(createdAt)}</p>
        ) : null}
      </div>
      <div className="flex items-center gap-2">
        <Link
          href="/packs"
          className="inline-flex h-7 items-center justify-center rounded-md border border-border bg-bg-elevated px-3 text-xs font-medium text-text-primary transition-colors hover:bg-bg-subtle"
        >
          Back to Packs
        </Link>
        <Button variant="secondary" size="sm" onClick={onToggleFailuresOnly}>
          {failuresOnly ? "Show All" : "Failures Only"}
        </Button>
        {canCancel ? (
          <Button
            variant="destructive"
            size="sm"
            onClick={onCancel}
            disabled={actionLoading !== null}
          >
            {actionLoading === "cancel" ? "Canceling…" : "Cancel Run"}
          </Button>
        ) : null}
        {canMarkFailed ? (
          <Button
            variant="secondary"
            size="sm"
            onClick={onMarkFailed}
            disabled={actionLoading !== null}
          >
            {actionLoading === "fail" ? "Marking…" : "Mark Failed"}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
