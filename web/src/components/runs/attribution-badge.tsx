import { StatusBadge } from "@/components/ui/badge";

interface AttributionBadgeProps {
  triggerSource?: string | null;
  scheduleId?: string | null;
}

function sourceLabel(triggerSource?: string | null, scheduleId?: string | null): string {
  const source = (triggerSource || "manual").toLowerCase();
  if (source === "scheduled") {
    return scheduleId ? `schedule:${scheduleId}` : "scheduled";
  }
  if (source === "api") {
    return "api";
  }
  return "manual";
}

function sourceVariant(triggerSource?: string | null): string {
  const source = (triggerSource || "manual").toLowerCase();
  if (source === "scheduled") {
    return "info";
  }
  if (source === "api") {
    return "warn";
  }
  return "pass";
}

export function AttributionBadge({ triggerSource, scheduleId }: AttributionBadgeProps) {
  return (
    <StatusBadge
      value={sourceVariant(triggerSource)}
      label={sourceLabel(triggerSource, scheduleId)}
    />
  );
}
