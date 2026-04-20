import type { ProviderCircuitState } from "@/lib/api/types";

type BadgeVariant = "pass" | "fail" | "warn" | "pending";

export function providerCircuitBadgeVariant(
  state: ProviderCircuitState["state"] | string | null | undefined
): BadgeVariant {
  const normalized = String(state ?? "").trim().toLowerCase();
  if (normalized === "open") {
    return "fail";
  }
  if (normalized === "half_open") {
    return "warn";
  }
  if (normalized === "closed") {
    return "pass";
  }
  return "pending";
}

export function providerCircuitAgeLabel(
  updatedAt: string | null | undefined,
  nowMs = Date.now()
): string {
  if (!updatedAt) {
    return "no signal";
  }
  const parsedMs = Date.parse(updatedAt);
  if (!Number.isFinite(parsedMs)) {
    return "invalid timestamp";
  }
  const ageS = Math.max(0, Math.floor((nowMs - parsedMs) / 1000));
  if (ageS < 60) {
    return `${ageS}s ago`;
  }
  if (ageS < 3600) {
    return `${Math.floor(ageS / 60)}m ago`;
  }
  return `${Math.floor(ageS / 3600)}h ago`;
}

function providerCircuitStateRank(state: ProviderCircuitState["state"] | string | null | undefined) {
  const normalized = String(state ?? "").trim().toLowerCase();
  if (normalized === "open") {
    return 0;
  }
  if (normalized === "half_open") {
    return 1;
  }
  if (normalized === "unknown") {
    return 2;
  }
  if (normalized === "closed") {
    return 3;
  }
  return 4;
}

export function sortProviderCircuits(
  circuits: readonly ProviderCircuitState[]
): ProviderCircuitState[] {
  return [...circuits].sort((left, right) => {
    const stateDelta = providerCircuitStateRank(left.state) - providerCircuitStateRank(right.state);
    if (stateDelta !== 0) {
      return stateDelta;
    }
    const leftKey = `${left.source}:${left.component}:${left.provider}:${left.service}`;
    const rightKey = `${right.source}:${right.component}:${right.provider}:${right.service}`;
    return leftKey.localeCompare(rightKey);
  });
}
