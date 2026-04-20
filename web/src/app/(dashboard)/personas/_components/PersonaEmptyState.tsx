"use client";

import Image from "next/image";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { bundledPersonaAvatars } from "@/lib/persona-avatars";
import type { PersonaTemplate } from "@/lib/persona-templates";

interface PersonaEmptyStateProps {
  onCreateClick: () => void;
  templates: PersonaTemplate[];
  onUseTemplate: (template: PersonaTemplate) => void;
}

export function PersonaEmptyState({
  onCreateClick,
  templates,
  onUseTemplate,
}: PersonaEmptyStateProps) {
  return (
    <div className="space-y-5">
      <Card className="overflow-hidden rounded-2xl">
        <CardBody className="grid gap-6 px-6 py-8 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="space-y-4">
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand">
                Persona Workspace
              </p>
              <h2 className="text-2xl font-semibold text-text-primary">
                Create your first persona
              </h2>
              <p className="max-w-2xl text-sm leading-6 text-text-secondary">
                Personas are reusable caller identities for AI scenarios. Give each one a name,
                portrait, tone, and short backstory so operators can understand the test actor at a
                glance.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button onClick={onCreateClick}>Create Persona</Button>
              <Button type="button" variant="secondary" onClick={onCreateClick}>
                Browse Starter Avatars
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            {bundledPersonaAvatars.slice(0, 3).map((avatar) => (
              <div
                key={avatar.id}
                className="rounded-2xl border border-border bg-bg-elevated p-2"
              >
                <div className="overflow-hidden rounded-xl">
                  <Image
                    src={avatar.url}
                    alt={avatar.label}
                    width={128}
                    height={128}
                    className="h-auto w-full object-cover"
                  />
                </div>
              </div>
            ))}
          </div>
        </CardBody>
      </Card>

      <div className="space-y-3">
        <div className="space-y-4">
          <div className="space-y-2">
            <h3 className="text-base font-semibold text-text-primary">Start from a default persona</h3>
            <p className="text-sm text-text-secondary">
              Use one of these as a starting point, then adjust prompt, tone, and avatar in the editor.
            </p>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            {templates.map((template) => (
              <button
                key={template.id}
                type="button"
                onClick={() => onUseTemplate(template)}
                className="flex cursor-pointer items-start gap-4 rounded-2xl border border-border bg-bg-surface p-4 text-left transition-colors hover:border-border-focus hover:bg-bg-elevated"
              >
                <div className="overflow-hidden rounded-2xl border border-border bg-bg-base shadow-sm">
                  <Image
                    src={template.avatarUrl}
                    alt={template.displayName}
                    width={88}
                    height={88}
                    className="h-24 w-24 object-cover"
                  />
                </div>
                <div className="min-w-0 space-y-2">
                  <div>
                    <p className="text-sm font-semibold text-text-primary">{template.displayName}</p>
                    <p className="text-xs text-text-secondary">{template.style}</p>
                  </div>
                  <p className="line-clamp-3 text-sm text-text-muted">
                    {template.backstorySummary}
                  </p>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
