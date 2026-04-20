export const SIDEBAR_PREFS_KEY = "botcheck:sidebar:v1";

interface LocalStorageLike {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
}

export interface SidebarPrefs {
  collapsed: boolean;
}

export function normalizeSidebarPrefs(raw: Partial<SidebarPrefs>): SidebarPrefs {
  return {
    collapsed: raw.collapsed ?? false,
  };
}

export function readSidebarPrefs(
  storage: LocalStorageLike | null | undefined =
    typeof window !== "undefined" ? window.localStorage : undefined
): SidebarPrefs | undefined {
  if (!storage) {
    return undefined;
  }
  try {
    const raw = storage.getItem(SIDEBAR_PREFS_KEY);
    if (!raw) {
      return undefined;
    }
    const parsed = JSON.parse(raw) as Partial<SidebarPrefs>;
    if (!parsed || typeof parsed !== "object") {
      return undefined;
    }
    return normalizeSidebarPrefs(parsed);
  } catch {
    return undefined;
  }
}

export function writeSidebarPrefs(
  prefs: SidebarPrefs,
  storage: LocalStorageLike | null | undefined =
    typeof window !== "undefined" ? window.localStorage : undefined
): void {
  if (!storage) {
    return;
  }
  try {
    storage.setItem(SIDEBAR_PREFS_KEY, JSON.stringify(normalizeSidebarPrefs(prefs)));
  } catch {
    // Ignore persistence failures.
  }
}
