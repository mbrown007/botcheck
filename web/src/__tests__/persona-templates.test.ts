import assert from "node:assert/strict";
import test from "node:test";
import { defaultPersonaTemplates } from "@/lib/persona-templates";

test("defaultPersonaTemplates exposes two starter personas", () => {
  assert.equal(defaultPersonaTemplates.length, 2);
  assert.equal(defaultPersonaTemplates[0]?.displayName, "Anxious Parent");
  assert.equal(defaultPersonaTemplates[1]?.displayName, "Pressed Account Manager");
});

test("defaultPersonaTemplates include avatar urls and prompts", () => {
  for (const template of defaultPersonaTemplates) {
    assert.ok(template.avatarUrl.startsWith("/personas/avatars/"));
    assert.ok(template.systemPrompt.length > 20);
  }
});
