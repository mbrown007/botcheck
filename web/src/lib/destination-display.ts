import type { BotDestinationSummary } from "@/lib/api";

type DestinationNameMap = Record<string, string>;

export function findTransportProfile(
  destinations: BotDestinationSummary[] | null | undefined,
  transportProfileId: string | null | undefined,
): BotDestinationSummary | null {
  const targetId = String(transportProfileId ?? "").trim();
  if (!targetId) {
    return null;
  }
  for (const destination of destinations ?? []) {
    if (
      destination.destination_id.trim() === targetId ||
      destination.transport_profile_id.trim() === targetId
    ) {
      return destination;
    }
  }
  return null;
}

export function destinationNameMap(
  destinations: BotDestinationSummary[] | null | undefined
): DestinationNameMap {
  const out: DestinationNameMap = {};
  for (const destination of destinations ?? []) {
    const id = destination.destination_id.trim();
    const transportProfileId = destination.transport_profile_id.trim();
    if (!id) {
      continue;
    }
    const label = destination.name.trim() || id;
    out[id] = label;
    if (transportProfileId) {
      out[transportProfileId] = label;
    }
  }
  return out;
}

export function destinationLabelForId(
  destinationId: string | null | undefined,
  namesById: DestinationNameMap
): string | null {
  const id = String(destinationId ?? "").trim();
  if (!id) {
    return null;
  }
  const name = namesById[id];
  if (!name || name === id) {
    return id;
  }
  return `${name} (${id})`;
}

function protocolLabel(protocol: string | null | undefined): string {
  const normalized = String(protocol ?? "").trim().toLowerCase();
  if (!normalized) return "Transport";
  return normalized.toUpperCase();
}

export function transportProfileOptionLabel(destination: BotDestinationSummary): string {
  const name = destination.name.trim() || destination.destination_id.trim();
  const protocol = protocolLabel(destination.protocol);
  if (destination.protocol === "sip" && destination.effective_channels) {
    return `${name} · ${protocol} · ${destination.effective_channels}ch${destination.is_active ? "" : " · inactive"}`;
  }
  return `${name} · ${protocol}${destination.is_active ? "" : " · inactive"}`;
}

function dispatchVerb(protocol: string | null | undefined): string {
  return String(protocol ?? "").trim().toLowerCase() === "http" ? "send requests to" : "dial";
}

export function describeTransportDispatch(params: {
  destinations: BotDestinationSummary[] | null | undefined;
  transportProfileId: string | null | undefined;
  dialTarget: string | null | undefined;
  fallbackTargetLabel: string;
}): string {
  const explicitTarget = String(params.dialTarget ?? "").trim();
  const profile = findTransportProfile(params.destinations, params.transportProfileId);
  const profileLabel =
    profile?.name.trim() || profile?.transport_profile_id.trim() || profile?.destination_id.trim() || "selected transport profile";
  const profileDefault = String(
    profile?.default_dial_target ?? profile?.endpoint ?? "",
  ).trim();
  const action = dispatchVerb(profile?.protocol);
  const targetLabel =
    String(profile?.protocol ?? "").trim().toLowerCase() === "http" ? "default endpoint" : "default dial target";

  if (explicitTarget && profile) {
    return `Will ${action} ${explicitTarget} via ${profileLabel}.`;
  }
  if (explicitTarget) {
    return `Will target ${explicitTarget} using the existing scenario transport settings.`;
  }
  if (profile && profileDefault) {
    return `Will use ${profileLabel}'s ${targetLabel}: ${profileDefault}.`;
  }
  if (profile) {
    return `This transport profile has no ${targetLabel}. If left blank, the ${params.fallbackTargetLabel} will be used.`;
  }
  return `If left blank, the ${params.fallbackTargetLabel} will be used.`;
}
