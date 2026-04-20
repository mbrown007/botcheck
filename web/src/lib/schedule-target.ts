import type { ScheduleResponse } from "@/lib/api";

type ScheduleLike = Pick<
  ScheduleResponse,
  "target_type" | "scenario_id" | "ai_scenario_id" | "pack_id" | "config_overrides"
>;

export function scheduleDestinationOverrideId(schedule: ScheduleLike): string | null {
  const overrides = schedule.config_overrides;
  if (!overrides || typeof overrides !== "object" || Array.isArray(overrides)) {
    return null;
  }
  const raw =
    (overrides as Record<string, unknown>).transport_profile_id ??
    (overrides as Record<string, unknown>).destination_id;
  if (typeof raw !== "string") {
    return null;
  }
  const trimmed = raw.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function scheduleBotEndpointOverride(schedule: ScheduleLike): string | null {
  const overrides = schedule.config_overrides;
  if (!overrides || typeof overrides !== "object" || Array.isArray(overrides)) {
    return null;
  }
  const raw =
    (overrides as Record<string, unknown>).dial_target ??
    (overrides as Record<string, unknown>).bot_endpoint;
  if (typeof raw !== "string") {
    return null;
  }
  const trimmed = raw.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function formatScheduleTargetLabel(
  schedule: ScheduleLike,
  aiScenarioIds?: Set<string>
): string {
  if (schedule.target_type === "pack") {
    return `pack:${schedule.pack_id ?? "—"}`;
  }
  if (schedule.ai_scenario_id) {
    return `scenario:${schedule.ai_scenario_id} · AI`;
  }
  const id = schedule.scenario_id ?? "—";
  if (aiScenarioIds && schedule.scenario_id && aiScenarioIds.has(schedule.scenario_id)) {
    return `scenario:${id} · AI`;
  }
  return `scenario:${id} · GRAPH`;
}
