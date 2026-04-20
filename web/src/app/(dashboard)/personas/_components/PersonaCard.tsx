"use client";

import Image from "next/image";
import { Copy, Pencil, Power, Trash2 } from "lucide-react";
import type { AIPersonaSummary, AIScenarioSummary } from "@/lib/api";
import { fallbackPersonaAvatarUrl } from "@/lib/persona-avatars";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

function linkedScenarioCount(
  personaId: string,
  scenarios: AIScenarioSummary[] | undefined
): number {
  return (scenarios ?? []).filter((scenario) => scenario.persona_id === personaId).length;
}

function formatUpdatedLabel(updatedAt: string): string {
  const parsed = new Date(updatedAt);
  if (Number.isNaN(parsed.getTime())) {
    return "Unknown";
  }
  return parsed.toLocaleString();
}

interface PersonaCardProps {
  persona: AIPersonaSummary;
  scenarios: AIScenarioSummary[] | undefined;
  index: number;
  editingPersonaId: string | null;
  duplicatingPersonaId: string | null;
  togglingPersonaId: string | null;
  deletingPersonaId: string | null;
  onEdit: (personaId: string) => void;
  onDuplicate: (personaId: string) => void;
  onToggleActive: (personaId: string, nextActive: boolean) => void;
  onDelete: (personaId: string) => void;
}

export function PersonaCard({
  persona,
  scenarios,
  index,
  editingPersonaId,
  duplicatingPersonaId,
  togglingPersonaId,
  deletingPersonaId,
  onEdit,
  onDuplicate,
  onToggleActive,
  onDelete,
}: PersonaCardProps) {
  const scenarioCount = linkedScenarioCount(persona.persona_id, scenarios);
  const avatarUrl = persona.avatar_url || fallbackPersonaAvatarUrl(index);
  const isEditing = editingPersonaId === persona.persona_id;
  const isDuplicating = duplicatingPersonaId === persona.persona_id;
  const isToggling = togglingPersonaId === persona.persona_id;
  const isDeleting = deletingPersonaId === persona.persona_id;
  const toggleActionClass = persona.is_active
    ? "border-fail-border bg-fail-bg/40 text-fail hover:bg-fail/10 hover:text-fail"
    : "border-pass-border bg-pass-bg/40 text-pass hover:bg-pass/10 hover:text-pass";

  return (
    <Card className="overflow-hidden rounded-2xl">
      <CardBody className="space-y-4 p-0">
        <div className="relative bg-gradient-to-br from-brand-muted via-bg-surface to-bg-elevated px-5 py-5">
          <div className="flex items-start gap-4">
            <div className="overflow-hidden rounded-2xl border border-border bg-bg-base shadow-sm">
              <Image
                src={avatarUrl}
                alt={persona.display_name}
                width={96}
                height={96}
                className="h-24 w-24 object-cover"
              />
            </div>
            <div className="min-w-0 flex-1 space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="truncate text-base font-semibold text-text-primary">
                  {persona.display_name}
                </h3>
                <StatusBadge
                  value={persona.is_active ? "pass" : "pending"}
                  label={persona.is_active ? "active" : "inactive"}
                />
              </div>
              <p className="font-mono text-[11px] text-text-muted">{persona.persona_id}</p>
              <div className="flex flex-wrap gap-2 text-xs">
                <span className="rounded-full border border-border bg-bg-base px-2 py-1 text-text-secondary">
                  {persona.style || "Style unset"}
                </span>
                <span className="rounded-full border border-border bg-bg-base px-2 py-1 text-text-secondary">
                  {persona.voice || "Voice unset"}
                </span>
                <span className="rounded-full border border-border bg-bg-base px-2 py-1 text-text-secondary">
                  {scenarioCount} linked scenario{scenarioCount === 1 ? "" : "s"}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-4 px-5 pb-5">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">
              Backstory
            </p>
            <p className="mt-1 line-clamp-3 text-sm text-text-secondary">
              {persona.backstory_summary || "No operator-facing backstory summary set."}
            </p>
          </div>
          <div className="flex items-start justify-between gap-4 border-t border-border pt-4">
            <p className="min-w-0 flex-1 text-xs text-text-muted">
              Updated {formatUpdatedLabel(persona.updated_at)}
            </p>
            <TooltipProvider delayDuration={120}>
              <div className="flex shrink-0 items-center justify-end gap-2">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      size="sm"
                      variant="secondary"
                      className="h-9 w-9 p-0"
                      onClick={() => onEdit(persona.persona_id)}
                      disabled={isEditing}
                      aria-label={isEditing ? "Opening persona" : "Edit persona"}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>{isEditing ? "Opening…" : "Edit"}</TooltipContent>
                </Tooltip>

                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      size="sm"
                      variant="secondary"
                      className="h-9 w-9 p-0"
                      onClick={() => onDuplicate(persona.persona_id)}
                      disabled={isDuplicating}
                      aria-label={isDuplicating ? "Duplicating persona" : "Duplicate persona"}
                    >
                      <Copy className="h-4 w-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>{isDuplicating ? "Duplicating…" : "Duplicate"}</TooltipContent>
                </Tooltip>

                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      size="sm"
                      variant="secondary"
                      className={`h-9 w-9 p-0 ${toggleActionClass}`}
                      onClick={() => onToggleActive(persona.persona_id, !persona.is_active)}
                      disabled={isToggling}
                      aria-label={
                        isToggling
                          ? persona.is_active
                            ? "Deactivating persona"
                            : "Activating persona"
                          : persona.is_active
                            ? "Deactivate persona"
                            : "Activate persona"
                      }
                    >
                      <Power className="h-4 w-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    {isToggling
                      ? persona.is_active
                        ? "Deactivating…"
                        : "Activating…"
                      : persona.is_active
                        ? "Deactivate"
                        : "Activate"}
                  </TooltipContent>
                </Tooltip>

                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      size="sm"
                      variant="secondary"
                      className="h-9 w-9 p-0 text-fail hover:text-fail"
                      onClick={() => onDelete(persona.persona_id)}
                      disabled={isDeleting}
                      aria-label={isDeleting ? "Deleting persona" : "Delete persona"}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>{isDeleting ? "Deleting…" : "Delete"}</TooltipContent>
                </Tooltip>
              </div>
            </TooltipProvider>
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
