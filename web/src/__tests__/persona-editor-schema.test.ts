import assert from "node:assert/strict";
import test from "node:test";
import { personaEditorFormSchema, createEmptyPersonaEditorValues, personaDetailToFormValues, personaFormValuesToPayload, personaTemplateToFormValues } from "@/lib/schemas/persona-editor";

test("createEmptyPersonaEditorValues uses bundled fallback avatar and active default", () => {
  const values = createEmptyPersonaEditorValues(1);
  assert.equal(values.avatarUrl, "/personas/avatars/female_avatar_2.png");
  assert.equal(values.isActive, true);
});

test("personaTemplateToFormValues maps starter persona template into form values", () => {
  const values = personaTemplateToFormValues({
    id: "template_one",
    displayName: "Anxious Parent",
    backstorySummary: "Summary",
    systemPrompt: "Prompt",
    style: "polite",
    voice: "alloy",
    avatarUrl: "/personas/avatars/female_avatar_1.png",
  });
  assert.equal(values.displayName, "Anxious Parent");
  assert.equal(values.handleName, "");
  assert.equal(values.isActive, true);
});

test("personaDetailToFormValues preserves existing persona identity values", () => {
  const values = personaDetailToFormValues({
    persona_id: "persona_123",
    name: "liam_white",
    display_name: "Liam White",
    avatar_url: null,
    backstory_summary: null,
    style: null,
    voice: null,
    is_active: false,
    created_at: "2026-03-08T00:00:00Z",
    updated_at: "2026-03-08T00:00:00Z",
    system_prompt: "Prompt text",
  });
  assert.equal(values.displayName, "Liam White");
  assert.equal(values.handleName, "liam_white");
  assert.equal(values.isActive, false);
});

test("personaFormValuesToPayload trims and normalizes optional values", () => {
  const payload = personaFormValuesToPayload({
    displayName: " Liam White ",
    handleName: " ",
    backstorySummary: " Summary ",
    systemPrompt: " Prompt ",
    style: " calm ",
    voice: " alloy ",
    avatarUrl: " /personas/avatars/female_avatar_1.png ",
    isActive: true,
  });
  assert.equal(payload.name, "liam_white");
  assert.equal(payload.display_name, "Liam White");
  assert.equal(payload.backstory_summary, "Summary");
  assert.equal(payload.system_prompt, "Prompt");
  assert.equal(payload.style, "calm");
  assert.equal(payload.voice, "alloy");
});

test("personaEditorFormSchema rejects blank required fields", () => {
  const result = personaEditorFormSchema.safeParse({
    displayName: " ",
    handleName: "",
    backstorySummary: "",
    systemPrompt: " ",
    style: "",
    voice: "",
    avatarUrl: "",
    isActive: true,
  });
  assert.equal(result.success, false);
});
