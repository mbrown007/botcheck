export const BUILDER_PANEL_PREFS_KEY = "botcheck:builder:panel_v1";
export const BUILDER_PANEL_WIDTH_MIN = 280;
export const BUILDER_PANEL_WIDTH_MAX = 640;
export const BUILDER_PANEL_WIDTH_DEFAULT = 440;

interface LocalStorageLike {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
}

export interface BuilderPanelPrefs {
  panelOpen: boolean;
  turnBlocksOpen: boolean;
  libraryOpen: boolean;
  metadataOpen: boolean;
  yamlOpen: boolean;
  panelWidth: number;
}

export function clampBuilderPanelWidth(width: number): number {
  return Math.min(BUILDER_PANEL_WIDTH_MAX, Math.max(BUILDER_PANEL_WIDTH_MIN, width));
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function normalizeBuilderPanelPrefs(
  raw: Partial<BuilderPanelPrefs>
): BuilderPanelPrefs {
  return {
    panelOpen: raw.panelOpen ?? true,
    turnBlocksOpen: raw.turnBlocksOpen ?? true,
    libraryOpen: raw.libraryOpen ?? true,
    metadataOpen: raw.metadataOpen ?? true,
    yamlOpen: raw.yamlOpen ?? true,
    panelWidth: clampBuilderPanelWidth(
      isFiniteNumber(raw.panelWidth) ? raw.panelWidth : BUILDER_PANEL_WIDTH_DEFAULT
    ),
  };
}

export function readBuilderPanelPrefs(
  storage: LocalStorageLike | null | undefined =
    typeof window !== "undefined" ? window.localStorage : undefined
): BuilderPanelPrefs | undefined {
  if (!storage) {
    return undefined;
  }
  try {
    const raw = storage.getItem(BUILDER_PANEL_PREFS_KEY);
    if (!raw) {
      return undefined;
    }
    const parsed = JSON.parse(raw) as Partial<BuilderPanelPrefs>;
    if (!parsed || typeof parsed !== "object") {
      return undefined;
    }
    return normalizeBuilderPanelPrefs(parsed);
  } catch {
    return undefined;
  }
}

export function writeBuilderPanelPrefs(
  prefs: BuilderPanelPrefs,
  storage: LocalStorageLike | null | undefined =
    typeof window !== "undefined" ? window.localStorage : undefined
): void {
  if (!storage) {
    return;
  }
  const normalized = normalizeBuilderPanelPrefs(prefs);
  try {
    storage.setItem(BUILDER_PANEL_PREFS_KEY, JSON.stringify(normalized));
  } catch {
    // Ignore persistence failures (private mode, quota exceeded, etc.).
  }
}
