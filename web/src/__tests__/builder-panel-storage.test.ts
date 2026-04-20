import test from "node:test";
import assert from "node:assert/strict";
import {
  BUILDER_PANEL_PREFS_KEY,
  BUILDER_PANEL_WIDTH_DEFAULT,
  BUILDER_PANEL_WIDTH_MAX,
  BUILDER_PANEL_WIDTH_MIN,
  clampBuilderPanelWidth,
  normalizeBuilderPanelPrefs,
  readBuilderPanelPrefs,
  writeBuilderPanelPrefs,
  type BuilderPanelPrefs,
} from "../lib/builder-panel-storage";

class MemoryStorage {
  private readonly map = new Map<string, string>();
  shouldThrowOnSet = false;
  shouldThrowOnGet = false;

  getItem(key: string): string | null {
    if (this.shouldThrowOnGet) {
      throw new Error("get failed");
    }
    return this.map.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    if (this.shouldThrowOnSet) {
      throw new Error("set failed");
    }
    this.map.set(key, value);
  }
}

test("clampBuilderPanelWidth clamps outside limits", () => {
  assert.equal(clampBuilderPanelWidth(BUILDER_PANEL_WIDTH_MIN - 20), BUILDER_PANEL_WIDTH_MIN);
  assert.equal(clampBuilderPanelWidth(BUILDER_PANEL_WIDTH_MAX + 20), BUILDER_PANEL_WIDTH_MAX);
  assert.equal(clampBuilderPanelWidth(420), 420);
});

test("normalizeBuilderPanelPrefs applies defaults and width fallback", () => {
  const normalized = normalizeBuilderPanelPrefs({
    panelOpen: false,
    panelWidth: Number.NaN,
  });
  assert.equal(normalized.panelOpen, false);
  assert.equal(normalized.turnBlocksOpen, true);
  assert.equal(normalized.libraryOpen, true);
  assert.equal(normalized.metadataOpen, true);
  assert.equal(normalized.yamlOpen, true);
  assert.equal(normalized.panelWidth, BUILDER_PANEL_WIDTH_DEFAULT);
});

test("readBuilderPanelPrefs returns undefined when no value stored", () => {
  const storage = new MemoryStorage();
  const prefs = readBuilderPanelPrefs(storage);
  assert.equal(prefs, undefined);
});

test("readBuilderPanelPrefs parses and normalizes stored payload", () => {
  const storage = new MemoryStorage();
  storage.setItem(
    BUILDER_PANEL_PREFS_KEY,
    JSON.stringify({
      panelOpen: false,
      turnBlocksOpen: false,
      libraryOpen: false,
      metadataOpen: false,
      yamlOpen: true,
      panelWidth: 999,
    })
  );

  const prefs = readBuilderPanelPrefs(storage);
  assert.deepEqual(prefs, {
    panelOpen: false,
    turnBlocksOpen: false,
    libraryOpen: false,
    metadataOpen: false,
    yamlOpen: true,
    panelWidth: BUILDER_PANEL_WIDTH_MAX,
  });
});

test("readBuilderPanelPrefs returns undefined on invalid JSON", () => {
  const storage = new MemoryStorage();
  storage.setItem(BUILDER_PANEL_PREFS_KEY, "{");
  const prefs = readBuilderPanelPrefs(storage);
  assert.equal(prefs, undefined);
});

test("writeBuilderPanelPrefs persists normalized payload", () => {
  const storage = new MemoryStorage();
  const prefs: BuilderPanelPrefs = {
    panelOpen: true,
    turnBlocksOpen: true,
    libraryOpen: false,
    metadataOpen: true,
    yamlOpen: true,
    panelWidth: 1200,
  };
  writeBuilderPanelPrefs(prefs, storage);

  const raw = storage.getItem(BUILDER_PANEL_PREFS_KEY);
  assert.ok(raw);
  const parsed = JSON.parse(raw) as BuilderPanelPrefs;
  assert.equal(parsed.panelWidth, BUILDER_PANEL_WIDTH_MAX);
  assert.equal(parsed.libraryOpen, false);
  assert.equal(parsed.turnBlocksOpen, true);
  assert.equal(parsed.metadataOpen, true);
});

test("writeBuilderPanelPrefs swallows storage set errors", () => {
  const storage = new MemoryStorage();
  storage.shouldThrowOnSet = true;
  writeBuilderPanelPrefs(
    {
      panelOpen: true,
      turnBlocksOpen: true,
      libraryOpen: true,
      metadataOpen: true,
      yamlOpen: true,
      panelWidth: BUILDER_PANEL_WIDTH_DEFAULT,
    },
    storage
  );
  assert.equal(storage.getItem(BUILDER_PANEL_PREFS_KEY), null);
});

test("readBuilderPanelPrefs swallows storage get errors", () => {
  const storage = new MemoryStorage();
  storage.shouldThrowOnGet = true;
  const prefs = readBuilderPanelPrefs(storage);
  assert.equal(prefs, undefined);
});
