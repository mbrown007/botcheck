import test from "node:test";
import assert from "node:assert/strict";
import {
  BUILDER_DRAFT_LAYOUT_SESSION_KEY,
  getOrCreateDraftLayoutSessionId,
} from "../lib/flow-layout-storage";

class MemoryStorage {
  private readonly map = new Map<string, string>();
  shouldThrowOnSet = false;

  getItem(key: string): string | null {
    return this.map.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    if (this.shouldThrowOnSet) {
      throw new Error("set failed");
    }
    this.map.set(key, value);
  }
}

test("getOrCreateDraftLayoutSessionId returns existing storage value", () => {
  const storage = new MemoryStorage();
  storage.setItem(BUILDER_DRAFT_LAYOUT_SESSION_KEY, "existing-session-id");

  const id = getOrCreateDraftLayoutSessionId(storage);

  assert.equal(id, "existing-session-id");
});

test("getOrCreateDraftLayoutSessionId persists a generated value when missing", () => {
  const storage = new MemoryStorage();

  const id = getOrCreateDraftLayoutSessionId(storage);

  assert.ok(id.length > 0);
  assert.equal(storage.getItem(BUILDER_DRAFT_LAYOUT_SESSION_KEY), id);
});

test("getOrCreateDraftLayoutSessionId falls back when storage is unavailable", () => {
  const id = getOrCreateDraftLayoutSessionId(undefined);

  assert.ok(id.length > 0);
});

test("getOrCreateDraftLayoutSessionId falls back when storage setItem throws", () => {
  const storage = new MemoryStorage();
  storage.shouldThrowOnSet = true;

  const id = getOrCreateDraftLayoutSessionId(storage);

  assert.ok(id.length > 0);
  assert.equal(storage.getItem(BUILDER_DRAFT_LAYOUT_SESSION_KEY), null);
});
