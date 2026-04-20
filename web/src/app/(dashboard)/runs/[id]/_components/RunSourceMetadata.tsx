"use client";

interface RunSourceMetadataProps {
  createdAt?: string | null;
  triggeredBy?: string | null;
  transport?: string | null;
  scheduleId?: string | null;
  transportProfileLabel?: string | null;
  transportProfileIdAtStart?: string | null;
  dialTargetAtStart?: string | null;
  capacityScopeAtStart?: string | null;
  capacityLimitAtStart?: number | null;
}

export function RunSourceMetadata({
  createdAt,
  triggeredBy,
  transport,
  scheduleId,
  transportProfileLabel,
  transportProfileIdAtStart,
  dialTargetAtStart,
  capacityScopeAtStart,
  capacityLimitAtStart,
}: RunSourceMetadataProps) {
  if (!createdAt) {
    return null;
  }

  return (
    <div className="space-y-1 text-xs text-text-muted">
      <p>Created {new Date(createdAt).toLocaleString()}</p>
      <p>
        Source metadata: triggered_by={triggeredBy ?? "—"} | transport={transport ?? "none"} |
        schedule_id={scheduleId ?? "—"}
      </p>
      {transportProfileIdAtStart ||
      dialTargetAtStart ||
      capacityScopeAtStart ||
      typeof capacityLimitAtStart === "number" ? (
        <p>
          Dispatch target: transport={transportProfileLabel ?? transportProfileIdAtStart ?? "—"} |
          target={dialTargetAtStart ?? "—"} |
          scope={capacityScopeAtStart ?? "—"} | capacity=
          {typeof capacityLimitAtStart === "number" ? capacityLimitAtStart : "—"}
        </p>
      ) : null}
    </div>
  );
}
