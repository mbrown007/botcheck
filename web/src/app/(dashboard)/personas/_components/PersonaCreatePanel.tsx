"use client";

import type { FieldErrors, UseFormRegister, UseFormSetValue, UseFormWatch } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import type { PersonaEditorFormValues } from "@/lib/schemas/persona-editor";
import { normalizePersonaHandle } from "@/lib/persona-avatars";
import { PersonaAvatarPicker } from "./PersonaAvatarPicker";

interface PersonaCreatePanelProps {
  mode: "create" | "edit";
  shell?: "card" | "plain";
  register: UseFormRegister<PersonaEditorFormValues>;
  watch: UseFormWatch<PersonaEditorFormValues>;
  setValue: UseFormSetValue<PersonaEditorFormValues>;
  errors: FieldErrors<PersonaEditorFormValues>;
  savingPersona: boolean;
  onSave: () => void | Promise<void>;
  onCancelEdit?: () => void;
}

export function PersonaCreatePanel({
  mode,
  shell = "card",
  register,
  watch,
  setValue,
  errors,
  savingPersona,
  onSave,
  onCancelEdit,
}: PersonaCreatePanelProps) {
  const displayName = watch("displayName");
  const handleName = watch("handleName");
  const avatarUrl = watch("avatarUrl");
  const effectiveHandle = normalizePersonaHandle(displayName, handleName);
  const isEdit = mode === "edit";

  const content = (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <label className="space-y-1.5">
          <span className="text-xs font-medium uppercase tracking-wide text-text-muted">
            Display Name
          </span>
          <input
            {...register("displayName")}
            placeholder="Liam White"
            className="w-full rounded-md border border-border bg-bg-base px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
          />
          {errors.displayName?.message ? (
            <p className="text-[11px] text-fail">{errors.displayName.message}</p>
          ) : null}
        </label>
        <label className="space-y-1.5">
          <span className="text-xs font-medium uppercase tracking-wide text-text-muted">
            Handle
          </span>
          <input
            {...register("handleName")}
            placeholder={effectiveHandle}
            className="w-full rounded-md border border-border bg-bg-base px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
          />
          <p className="text-[11px] text-text-muted">
            Stable internal name. Defaults to <span className="font-mono">{effectiveHandle}</span>.
          </p>
        </label>
      </div>

      <label className="space-y-1.5">
        <span className="text-xs font-medium uppercase tracking-wide text-text-muted">
          Backstory Summary
        </span>
        <textarea
          {...register("backstorySummary")}
          placeholder="Polite parent travelling with two small children after hearing their Ryanair flight is delayed."
          rows={3}
          className="w-full rounded-md border border-border bg-bg-base px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
        />
      </label>

      <div className="grid gap-4 lg:grid-cols-2">
        <label className="space-y-1.5">
          <span className="text-xs font-medium uppercase tracking-wide text-text-muted">
            Style
          </span>
          <input
            {...register("style")}
            placeholder="calm but worried"
            className="w-full rounded-md border border-border bg-bg-base px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
          />
        </label>
        <label className="space-y-1.5">
          <span className="text-xs font-medium uppercase tracking-wide text-text-muted">
            Voice
          </span>
          <input
            {...register("voice")}
            placeholder="alloy"
            className="w-full rounded-md border border-border bg-bg-base px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
          />
        </label>
      </div>

      <PersonaAvatarPicker
        selectedAvatarUrl={avatarUrl}
        onSelect={(value) => setValue("avatarUrl", value, { shouldDirty: true, shouldValidate: true })}
      />

      <label className="flex items-center gap-2 rounded-md border border-border bg-bg-base px-3 py-2 text-sm text-text-primary">
        <input
          {...register("isActive")}
          type="checkbox"
          className="h-4 w-4 rounded border-border"
        />
        <span>Active and available for new AI scenarios</span>
      </label>

      <label className="space-y-1.5">
        <span className="text-xs font-medium uppercase tracking-wide text-text-muted">
          System Prompt
        </span>
        <textarea
          {...register("systemPrompt")}
          placeholder="Stay in role as Liam White. You are polite, concise, and trying to confirm whether your delayed flight will still depart today."
          rows={8}
          className="w-full rounded-md border border-border bg-bg-base px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
        />
        {errors.systemPrompt?.message ? (
          <p className="text-[11px] text-fail">{errors.systemPrompt.message}</p>
        ) : null}
      </label>

      <div className="flex justify-end">
        <div className="flex gap-2">
          {isEdit && onCancelEdit ? (
            <Button variant="secondary" onClick={onCancelEdit} disabled={savingPersona}>
              Cancel
            </Button>
          ) : null}
          <Button onClick={onSave} disabled={savingPersona}>
            {savingPersona
              ? isEdit
                ? "Saving…"
                : "Creating…"
              : isEdit
                ? "Save Persona"
                : "Create Persona"}
          </Button>
        </div>
      </div>
    </div>
  );

  if (shell === "plain") {
    return content;
  }

  return (
    <Card className="rounded-2xl">
      <CardHeader>
        <div>
          <p className="text-sm font-medium text-text-primary">
            {isEdit ? "Edit Persona" : "Create Persona"}
          </p>
          <p className="mt-1 text-xs text-text-muted">
            {isEdit
              ? "Update the operator-facing identity and runtime prompt for this persona."
              : "Define the reusable caller identity your AI scenarios will role-play."}
          </p>
        </div>
      </CardHeader>
      <CardBody>{content}</CardBody>
    </Card>
  );
}
