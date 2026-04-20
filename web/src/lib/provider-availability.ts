import type {
  ProviderAvailabilitySummaryResponse,
  SpeechCapabilities,
  SpeechProviderCapability,
} from "@/lib/api";

type SpeechKind = "tts" | "stt";
export type ProviderCapabilityKind = "tts" | "stt" | "llm" | "judge";

const KNOWN_SPEECH_CAPABILITIES: Record<SpeechKind, Record<string, SpeechProviderCapability>> = {
  tts: {
    openai: {
      id: "openai",
      label: "OpenAI",
      enabled: false,
      voice_mode: "static_select",
      supports_preview: true,
      supports_cache_warm: true,
      supports_live_synthesis: true,
      supports_live_stream: true,
    },
    elevenlabs: {
      id: "elevenlabs",
      label: "ElevenLabs",
      enabled: false,
      voice_mode: "freeform_id",
      supports_preview: true,
      supports_cache_warm: true,
      supports_live_synthesis: true,
      supports_live_stream: false,
    },
  },
  stt: {
    deepgram: {
      id: "deepgram",
      label: "Deepgram",
      enabled: false,
      voice_mode: "freeform_id",
      supports_preview: false,
      supports_cache_warm: false,
      supports_live_synthesis: false,
      supports_live_stream: true,
    },
    azure: {
      id: "azure",
      label: "Azure Speech",
      enabled: false,
      voice_mode: "freeform_id",
      supports_preview: false,
      supports_cache_warm: false,
      supports_live_synthesis: false,
      supports_live_stream: true,
    },
  },
};

const CAPABILITY_ORDER: ProviderCapabilityKind[] = ["tts", "stt", "llm", "judge"];

function vendorLabel(vendor: string): string {
  const normalized = vendor.trim().toLowerCase();
  if (!normalized) {
    return "Unknown";
  }
  if (normalized === "openai") {
    return "OpenAI";
  }
  if (normalized === "elevenlabs") {
    return "ElevenLabs";
  }
  if (normalized === "deepgram") {
    return "Deepgram";
  }
  if (normalized === "azure") {
    return "Azure Speech";
  }
  if (normalized === "anthropic") {
    return "Anthropic";
  }
  return normalized.replace(/[-_]/g, " ").replace(/\b\w/g, (match) => match.toUpperCase());
}

function genericSpeechCapability(
  kind: SpeechKind,
  vendor: string,
  enabled: boolean
): SpeechProviderCapability {
  return {
    id: vendor,
    label: vendorLabel(vendor),
    enabled,
    voice_mode: "freeform_id",
    supports_preview: false,
    supports_cache_warm: false,
    supports_live_synthesis: kind === "tts",
    supports_live_stream: true,
  };
}

function buildSpeechCapabilitiesForKind(
  kind: SpeechKind,
  providers: ProviderAvailabilitySummaryResponse[],
  fallback: SpeechProviderCapability[] | undefined
): SpeechProviderCapability[] {
  const vendorEnabled = new Set(
    providers
      .filter((item) => item.capability === kind)
      .map((item) => item.vendor.trim().toLowerCase())
      .filter(Boolean)
  );
  const entries = new Map<string, SpeechProviderCapability>();

  for (const capability of Object.values(KNOWN_SPEECH_CAPABILITIES[kind])) {
    entries.set(capability.id, {
      ...capability,
      enabled: vendorEnabled.has(capability.id),
    });
  }

  for (const capability of fallback ?? []) {
    const id = capability.id.trim().toLowerCase();
    if (!id) {
      continue;
    }
    entries.set(id, {
      ...capability,
      id,
      enabled: vendorEnabled.has(id),
    });
  }

  for (const vendor of vendorEnabled) {
    if (!entries.has(vendor)) {
      entries.set(vendor, genericSpeechCapability(kind, vendor, true));
    }
  }

  return [...entries.values()].sort((left, right) => left.label.localeCompare(right.label));
}

export function buildSpeechCapabilitiesFromAvailableProviders(
  providers: ProviderAvailabilitySummaryResponse[] | undefined,
  fallback: SpeechCapabilities | undefined
): SpeechCapabilities | undefined {
  if (providers === undefined) {
    return fallback;
  }
  return {
    tts: buildSpeechCapabilitiesForKind("tts", providers, fallback?.tts),
    stt: buildSpeechCapabilitiesForKind("stt", providers, fallback?.stt),
  };
}

export function filterAvailableProvidersByCapability(
  providers: ProviderAvailabilitySummaryResponse[] | undefined,
  capability: ProviderCapabilityKind
): ProviderAvailabilitySummaryResponse[] {
  return (providers ?? [])
    .filter((item) => item.capability === capability)
    .sort((left, right) => {
      const vendorSort = left.vendor.localeCompare(right.vendor);
      return vendorSort !== 0 ? vendorSort : left.model.localeCompare(right.model);
    });
}

export function formatAvailableProviderLabel(item: ProviderAvailabilitySummaryResponse): string {
  return `${item.vendor}:${item.model}`;
}

export function formatProviderCredentialSource(source: string): string {
  const normalized = source.trim().toLowerCase();
  if (normalized === "db_encrypted") {
    return "stored";
  }
  if (normalized === "env") {
    return "env";
  }
  return normalized || "unknown";
}

export function groupAvailableProvidersByCapability(
  providers: ProviderAvailabilitySummaryResponse[] | undefined,
  capabilities: ProviderCapabilityKind[]
): Array<{
  capability: ProviderCapabilityKind;
  items: ProviderAvailabilitySummaryResponse[];
}> {
  const requested = [...new Set(capabilities)].sort(
    (left, right) => CAPABILITY_ORDER.indexOf(left) - CAPABILITY_ORDER.indexOf(right)
  );
  return requested.map((capability) => ({
    capability,
    items: filterAvailableProvidersByCapability(providers, capability),
  }));
}
