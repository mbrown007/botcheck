import assert from "node:assert/strict";
import test from "node:test";
import {
  SIDEBAR_PREFS_KEY,
  normalizeSidebarPrefs,
  readSidebarPrefs,
  writeSidebarPrefs,
} from "@/lib/sidebar-state";

function makeStorage(seed?: Record<string, string>) {
  const store = new Map(Object.entries(seed ?? {}));
  return {
    getItem(key: string) {
      return store.get(key) ?? null;
    },
    setItem(key: string, value: string) {
      store.set(key, value);
    },
    dump() {
      return Object.fromEntries(store.entries());
    },
  };
}

test("normalizeSidebarPrefs defaults collapsed to false", () => {
  assert.deepEqual(normalizeSidebarPrefs({}), { collapsed: false });
  assert.deepEqual(normalizeSidebarPrefs({ collapsed: true }), { collapsed: true });
});

test("readSidebarPrefs returns normalized persisted preferences", () => {
  const storage = makeStorage({
    [SIDEBAR_PREFS_KEY]: JSON.stringify({ collapsed: true }),
  });

  assert.deepEqual(readSidebarPrefs(storage), { collapsed: true });
});

test("readSidebarPrefs returns undefined for invalid persisted values", () => {
  assert.equal(readSidebarPrefs(makeStorage()), undefined);
  assert.equal(readSidebarPrefs(makeStorage({ [SIDEBAR_PREFS_KEY]: "not-json" })), undefined);
  assert.equal(readSidebarPrefs(makeStorage({ [SIDEBAR_PREFS_KEY]: "\"bad\"" })), undefined);
});

test("writeSidebarPrefs persists normalized preferences", () => {
  const storage = makeStorage();

  writeSidebarPrefs({ collapsed: true }, storage);

  assert.deepEqual(storage.dump(), {
    [SIDEBAR_PREFS_KEY]: JSON.stringify({ collapsed: true }),
  });
});

test("writeSidebarPrefs swallows storage failures", () => {
  const storage = {
    getItem() {
      return null;
    },
    setItem() {
      throw new Error("quota");
    },
  };

  assert.doesNotThrow(() => writeSidebarPrefs({ collapsed: false }, storage));
});
