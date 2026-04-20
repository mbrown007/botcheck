import type { SpeechCapabilities, SpeechProviderCapability } from "@/lib/api";

export const OPENAI_TTS_VOICE_OPTIONS = [
  { id: "alloy", label: "Alloy" },
  { id: "ash", label: "Ash" },
  { id: "ballad", label: "Ballad" },
  { id: "coral", label: "Coral" },
  { id: "echo", label: "Echo" },
  { id: "fable", label: "Fable" },
  { id: "nova", label: "Nova" },
  { id: "onyx", label: "Onyx" },
  { id: "sage", label: "Sage" },
  { id: "shimmer", label: "Shimmer" },
] as const;

const DEFAULT_TTS_PROVIDER_ID = "openai";
const DEFAULT_STT_PROVIDER_ID = "deepgram";
const DEFAULT_DEEPGRAM_STT_MODEL = "nova-2-general";
const DEFAULT_AZURE_STT_MODEL = "azure-default";

const FALLBACK_TTS_CAPABILITIES: SpeechProviderCapability[] = [
  {
    id: "openai",
    label: "OpenAI",
    enabled: true,
    voice_mode: "static_select",
    supports_preview: true,
    supports_cache_warm: true,
    supports_live_synthesis: true,
    supports_live_stream: true,
  },
];

const FALLBACK_STT_CAPABILITIES: SpeechProviderCapability[] = [
  {
    id: "deepgram",
    label: "Deepgram",
    enabled: true,
    voice_mode: "freeform_id",
    supports_preview: false,
    supports_cache_warm: false,
    supports_live_synthesis: false,
    supports_live_stream: true,
  },
];

interface ParsedAuthoringTtsVoice {
  raw: string;
  providerId: string;
  voice: string;
  canonical: string;
  isEmpty: boolean;
  isIncomplete: boolean;
  usesImplicitProvider: boolean;
}

export interface TtsAuthoringState {
  parsed: ParsedAuthoringTtsVoice;
  availableProviders: SpeechProviderCapability[];
  allProviders: SpeechProviderCapability[];
  activeProvider: SpeechProviderCapability | null;
  displayProviderId: string;
  displayVoice: string;
  currentProviderUnavailable: boolean;
}

export interface SttAuthoringState {
  availableProviders: SpeechProviderCapability[];
  allProviders: SpeechProviderCapability[];
  activeProvider: SpeechProviderCapability | null;
  displayProviderId: string;
  displayModel: string;
  currentProviderUnavailable: boolean;
}

function normalizeProviderId(
  value: string,
  fallbackProviderId: string = DEFAULT_TTS_PROVIDER_ID
): string {
  return value.trim().toLowerCase() || fallbackProviderId;
}

function getSpeechCapabilitiesByKind(
  kind: "tts" | "stt",
  speechCapabilities?: SpeechCapabilities
): SpeechProviderCapability[] {
  const configuredCapabilities =
    kind === "tts" ? speechCapabilities?.tts : speechCapabilities?.stt;
  if (Array.isArray(configuredCapabilities) && configuredCapabilities.length > 0) {
    return configuredCapabilities;
  }
  return kind === "tts" ? FALLBACK_TTS_CAPABILITIES : FALLBACK_STT_CAPABILITIES;
}

export function parseAuthoringTtsVoice(rawValue: string): ParsedAuthoringTtsVoice {
  const raw = rawValue.trim();
  if (!raw) {
    return {
      raw,
      providerId: "",
      voice: "",
      canonical: "",
      isEmpty: true,
      isIncomplete: false,
      usesImplicitProvider: false,
    };
  }

  if (!raw.includes(":")) {
    return {
      raw,
      providerId: DEFAULT_TTS_PROVIDER_ID,
      voice: raw,
      canonical: `${DEFAULT_TTS_PROVIDER_ID}:${raw}`,
      isEmpty: false,
      isIncomplete: raw.length === 0,
      usesImplicitProvider: true,
    };
  }

  const [providerPart, ...voiceParts] = raw.split(":");
  const providerId = normalizeProviderId(providerPart);
  const voice = voiceParts.join(":").trim();

  return {
    raw,
    providerId,
    voice,
    canonical: `${providerId}:${voice}`,
    isEmpty: false,
    isIncomplete: voice.length === 0,
    usesImplicitProvider: false,
  };
}

function getAllTtsCapabilities(
  speechCapabilities?: SpeechCapabilities
): SpeechProviderCapability[] {
  return getSpeechCapabilitiesByKind("tts", speechCapabilities);
}

function getEnabledTtsCapabilities(
  speechCapabilities?: SpeechCapabilities
): SpeechProviderCapability[] {
  return getAllTtsCapabilities(speechCapabilities).filter((capability) => capability.enabled);
}

function getDefaultTtsProviderId(
  speechCapabilities?: SpeechCapabilities
): string {
  return getEnabledTtsCapabilities(speechCapabilities)[0]?.id ?? DEFAULT_TTS_PROVIDER_ID;
}

export function getDefaultVoiceForTtsProvider(providerId: string): string {
  if (normalizeProviderId(providerId) === "openai") {
    return "nova";
  }
  return "";
}

function getAllSttCapabilities(
  speechCapabilities?: SpeechCapabilities
): SpeechProviderCapability[] {
  return getSpeechCapabilitiesByKind("stt", speechCapabilities);
}

function getEnabledSttCapabilities(
  speechCapabilities?: SpeechCapabilities
): SpeechProviderCapability[] {
  return getAllSttCapabilities(speechCapabilities).filter((capability) => capability.enabled);
}

export function getDefaultSttProviderId(
  speechCapabilities?: SpeechCapabilities
): string {
  return getEnabledSttCapabilities(speechCapabilities)[0]?.id ?? DEFAULT_STT_PROVIDER_ID;
}

export function getDefaultModelForSttProvider(providerId: string): string {
  const normalizedProviderId = providerId.trim().toLowerCase();
  if (normalizedProviderId === DEFAULT_STT_PROVIDER_ID) {
    return DEFAULT_DEEPGRAM_STT_MODEL;
  }
  if (normalizedProviderId === "azure") {
    return DEFAULT_AZURE_STT_MODEL;
  }
  return "";
}

export function buildCanonicalTtsVoice(providerId: string, voice: string): string {
  const normalizedProvider = normalizeProviderId(providerId);
  const normalizedVoice = voice.trim();
  if (!normalizedProvider) {
    return "";
  }
  if (!normalizedVoice) {
    return `${normalizedProvider}:`;
  }
  return `${normalizedProvider}:${normalizedVoice}`;
}

export function deriveTtsAuthoringState(
  rawTtsVoice: string,
  speechCapabilities?: SpeechCapabilities
): TtsAuthoringState {
  const parsed = parseAuthoringTtsVoice(rawTtsVoice);
  const allProviders = getAllTtsCapabilities(speechCapabilities);
  const availableProviders = allProviders.filter((capability) => capability.enabled);
  const hasCurrentEnabledProvider =
    !parsed.isEmpty &&
    availableProviders.some((capability) => capability.id === parsed.providerId);
  const currentProviderUnavailable = !parsed.isEmpty && !hasCurrentEnabledProvider;

  const displayProviderId = currentProviderUnavailable
    ? ""
    : parsed.providerId || getDefaultTtsProviderId(speechCapabilities);
  const activeProvider =
    availableProviders.find((capability) => capability.id === displayProviderId) ?? null;
  const displayVoice =
    parsed.isEmpty || currentProviderUnavailable
      ? getDefaultVoiceForTtsProvider(displayProviderId)
      : parsed.voice;

  return {
    parsed,
    availableProviders,
    allProviders,
    activeProvider,
    displayProviderId,
    displayVoice,
    currentProviderUnavailable,
  };
}

export function deriveSttAuthoringState(
  rawSttProvider: string,
  rawSttModel: string,
  speechCapabilities?: SpeechCapabilities
): SttAuthoringState {
  const allProviders = getAllSttCapabilities(speechCapabilities);
  const availableProviders = allProviders.filter((capability) => capability.enabled);
  const normalizedProviderId = normalizeProviderId(
    rawSttProvider,
    DEFAULT_STT_PROVIDER_ID
  );
  const hasCurrentEnabledProvider = availableProviders.some(
    (capability) => capability.id === normalizedProviderId
  );
  const currentProviderUnavailable =
    rawSttProvider.trim().length > 0 && !hasCurrentEnabledProvider;
  const displayProviderId = currentProviderUnavailable
    ? ""
    : normalizedProviderId || getDefaultSttProviderId(speechCapabilities);
  const activeProvider =
    availableProviders.find((capability) => capability.id === displayProviderId) ?? null;

  return {
    availableProviders,
    allProviders,
    activeProvider,
    displayProviderId,
    displayModel:
      rawSttModel.trim() || getDefaultModelForSttProvider(displayProviderId || "deepgram"),
    currentProviderUnavailable,
  };
}
