import { z } from "zod";
import type { AIPersonaDetail, AIPersonaUpsertRequest } from "@/lib/api";
import type { PersonaTemplate } from "@/lib/persona-templates";
import { fallbackPersonaAvatarUrl, normalizePersonaHandle } from "@/lib/persona-avatars";

export const personaEditorFormSchema = z.object({
  displayName: z.string().trim().min(1, "Display name is required.").max(255),
  handleName: z.string().trim().max(255),
  backstorySummary: z.string().max(2000),
  systemPrompt: z.string().trim().min(1, "System prompt is required.").max(12000),
  style: z.string().max(128),
  voice: z.string().max(128),
  avatarUrl: z.string().max(512),
  isActive: z.boolean(),
});

export type PersonaEditorFormValues = z.infer<typeof personaEditorFormSchema>;

export function createEmptyPersonaEditorValues(fallbackAvatarIndex = 0): PersonaEditorFormValues {
  return {
    displayName: "",
    handleName: "",
    backstorySummary: "",
    systemPrompt: "",
    style: "",
    voice: "",
    avatarUrl: fallbackPersonaAvatarUrl(fallbackAvatarIndex),
    isActive: true,
  };
}

export function personaTemplateToFormValues(
  template: PersonaTemplate
): PersonaEditorFormValues {
  return {
    displayName: template.displayName,
    handleName: "",
    backstorySummary: template.backstorySummary,
    systemPrompt: template.systemPrompt,
    style: template.style,
    voice: template.voice,
    avatarUrl: template.avatarUrl,
    isActive: true,
  };
}

export function personaDetailToFormValues(
  detail: AIPersonaDetail,
  fallbackAvatarIndex = 0
): PersonaEditorFormValues {
  return {
    displayName: detail.display_name || detail.name,
    handleName: detail.name,
    backstorySummary: detail.backstory_summary || "",
    systemPrompt: detail.system_prompt,
    style: detail.style || "",
    voice: detail.voice || "",
    avatarUrl: detail.avatar_url || fallbackPersonaAvatarUrl(fallbackAvatarIndex),
    isActive: detail.is_active,
  };
}

export function personaFormValuesToPayload(
  values: PersonaEditorFormValues
): AIPersonaUpsertRequest {
  const displayName = values.displayName.trim();
  const handleName = values.handleName.trim();
  return {
    name: normalizePersonaHandle(displayName, handleName),
    display_name: displayName,
    avatar_url: values.avatarUrl.trim() || undefined,
    backstory_summary: values.backstorySummary.trim() || undefined,
    system_prompt: values.systemPrompt.trim(),
    style: values.style.trim() || undefined,
    voice: values.voice.trim() || undefined,
    is_active: values.isActive,
  };
}
