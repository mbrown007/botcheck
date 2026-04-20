"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { zodResolver } from "@hookform/resolvers/zod";
import Image from "next/image";
import { X } from "lucide-react";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import {
  personaEditorFormSchema,
  personaTemplateToFormValues,
  type PersonaEditorFormValues,
} from "@/lib/schemas/persona-editor";
import { PersonaCreatePanel } from "./PersonaCreatePanel";
import type { PersonaTemplate } from "@/lib/persona-templates";

interface PersonaEditorDialogProps {
  open: boolean;
  mode: "create" | "edit";
  initialValues: PersonaEditorFormValues;
  savingPersona: boolean;
  templates: PersonaTemplate[];
  onOpenChange: (open: boolean) => void;
  onSave: (values: PersonaEditorFormValues) => void | Promise<void>;
  onCancelEdit: () => void;
}

export function PersonaEditorDialog({
  open,
  mode,
  initialValues,
  savingPersona,
  templates,
  onOpenChange,
  onSave,
  onCancelEdit,
}: PersonaEditorDialogProps) {
  const isEdit = mode === "edit";
  const form = useForm<PersonaEditorFormValues>({
    resolver: zodResolver(personaEditorFormSchema),
    mode: "onChange",
    defaultValues: initialValues,
  });
  const {
    register,
    watch,
    setValue,
    reset,
    handleSubmit,
    formState: { errors },
  } = form;

  useEffect(() => {
    reset(initialValues);
  }, [initialValues, reset]);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-overlay/70 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-[60] w-[min(92vw,72rem)] max-h-[88vh] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl border border-border bg-bg-surface p-6 shadow-xl">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <Dialog.Title className="text-lg font-semibold text-text-primary">
                {isEdit ? "Edit Persona" : "Create Persona"}
              </Dialog.Title>
              <Dialog.Description className="max-w-2xl text-sm text-text-secondary">
                Build reusable caller identities with a clear display name, portrait, backstory,
                and runtime prompt.
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                aria-label="Close persona editor"
                className="rounded-md border border-border bg-bg-base p-2 text-text-muted transition-colors hover:text-text-primary"
              >
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          {!isEdit ? (
            <div className="mt-5 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-text-primary">Starter personas</p>
                  <p className="text-xs text-text-muted">
                    Use a starter as a base, then adjust tone, prompt, and avatar as needed.
                  </p>
                </div>
              </div>
              <div className="grid gap-3 lg:grid-cols-2">
                {templates.map((template) => (
                  <button
                    key={template.id}
                    type="button"
                    onClick={() => reset(personaTemplateToFormValues(template))}
                    className="flex cursor-pointer items-start gap-3 rounded-2xl border border-border bg-bg-base p-3 text-left transition-colors hover:border-border-focus hover:bg-bg-elevated"
                  >
                    <div className="overflow-hidden rounded-xl border border-border bg-bg-surface">
                      <Image
                        src={template.avatarUrl}
                        alt={template.displayName}
                        width={64}
                        height={64}
                        className="h-16 w-16 object-cover"
                      />
                    </div>
                    <div className="min-w-0 space-y-1">
                      <p className="text-sm font-semibold text-text-primary">{template.displayName}</p>
                      <p className="text-xs text-text-secondary">{template.style}</p>
                      <p className="line-clamp-2 text-xs text-text-muted">
                        {template.backstorySummary}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          <div className="mt-5">
            <PersonaCreatePanel
              mode={mode}
              shell="plain"
              register={register}
              watch={watch}
              setValue={setValue}
              errors={errors}
              savingPersona={savingPersona}
              onSave={handleSubmit(onSave)}
              onCancelEdit={onCancelEdit}
            />
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
