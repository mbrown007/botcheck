import assert from "node:assert/strict";
import test from "node:test";
import {
  bundledPersonaAvatars,
  fallbackPersonaAvatarUrl,
  normalizePersonaHandle,
} from "@/lib/persona-avatars";

test("bundledPersonaAvatars exposes the shipped avatar catalog", () => {
  assert.equal(bundledPersonaAvatars.length, 12);
  assert.equal(bundledPersonaAvatars[0]?.url, "/personas/avatars/female_avatar_1.png");
  assert.equal(bundledPersonaAvatars.at(-1)?.url, "/personas/avatars/male_avatar_4.png");
});

test("fallbackPersonaAvatarUrl wraps indexes safely", () => {
  assert.equal(fallbackPersonaAvatarUrl(0), "/personas/avatars/female_avatar_1.png");
  assert.equal(fallbackPersonaAvatarUrl(12), "/personas/avatars/female_avatar_1.png");
});

test("normalizePersonaHandle slugs explicit or derived names", () => {
  assert.equal(normalizePersonaHandle("Liam White"), "liam_white");
  assert.equal(normalizePersonaHandle("Liam White", " Caller 01 "), "caller_01");
  assert.equal(normalizePersonaHandle("!!!"), "persona");
});
