"use client";

import React from "react";
import { Card, CardBody } from "@/components/ui/card";
import type { ScheduleResponse } from "@/lib/api";
import { SCHEDULE_ALERT_THRESHOLD } from "@/components/dashboard/tenant-dashboard-data";

function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string | number;
  sub?: string;
  accent?: string;
}) {
  return (
    <Card>
      <CardBody className="py-3">
        <p className="text-xs uppercase tracking-wide text-text-muted">{label}</p>
        <p className={`mt-1 text-2xl font-semibold ${accent ?? "text-text-primary"}`}>{value}</p>
        {sub ? <p className="mt-0.5 text-xs text-text-muted">{sub}</p> : null}
      </CardBody>
    </Card>
  );
}

export function SchedulesDashboard({ schedules }: { schedules: ScheduleResponse[] }) {
  if (!schedules.length) {
    return null;
  }

  const total = schedules.length;
  const active = schedules.filter((row) => row.active).length;
  const retryEnabled = schedules.filter((row) => row.retry_on_failure).length;
  const streaking = schedules.filter((row) => (row.consecutive_failures ?? 0) > 0).length;
  const alerting = schedules.filter((row) => (row.consecutive_failures ?? 0) >= SCHEDULE_ALERT_THRESHOLD).length;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatCard label="Total Schedules" value={total} sub="configured" />
      <StatCard
        label="Active"
        value={active}
        sub="dispatching on cron"
        accent={active > 0 ? "text-brand" : "text-text-primary"}
      />
      <StatCard
        label="Retry Enabled"
        value={retryEnabled}
        sub="single scenario only"
        accent={retryEnabled > 0 ? "text-pass" : "text-text-primary"}
      />
      <StatCard
        label="Failure Streaks"
        value={streaking}
        sub={alerting > 0 ? `${alerting} at 2+ failures` : "no alerting streaks"}
        accent={alerting > 0 ? "text-fail" : streaking > 0 ? "text-warn" : "text-pass"}
      />
    </div>
  );
}
