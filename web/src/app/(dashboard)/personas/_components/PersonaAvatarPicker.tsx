"use client";

import Image from "next/image";
import { bundledPersonaAvatars } from "@/lib/persona-avatars";
import { cn } from "@/lib/utils";

interface PersonaAvatarPickerProps {
  selectedAvatarUrl: string;
  onSelect: (avatarUrl: string) => void;
}

export function PersonaAvatarPicker({
  selectedAvatarUrl,
  onSelect,
}: PersonaAvatarPickerProps) {
  return (
    <div className="space-y-3">
      <div>
        <p className="text-sm font-medium text-text-primary">Starter Avatar</p>
        <p className="text-xs text-text-muted">
          Pick a starter portrait for this persona identity. Custom uploads can come later.
        </p>
      </div>
      <div className="grid grid-cols-4 gap-3 sm:grid-cols-6">
        {bundledPersonaAvatars.map((avatar) => {
          const active = avatar.url === selectedAvatarUrl;
          return (
            <button
              key={avatar.id}
              type="button"
              onClick={() => onSelect(avatar.url)}
              className={cn(
                "group rounded-2xl border p-1.5 transition-all",
                active
                  ? "border-brand bg-brand-muted ring-2 ring-brand/20"
                  : "border-border bg-bg-base hover:border-brand/50 hover:bg-bg-elevated"
              )}
              aria-label={avatar.label}
              title={avatar.label}
            >
              <div className="overflow-hidden rounded-xl">
                <Image
                  src={avatar.url}
                  alt={avatar.label}
                  width={120}
                  height={120}
                  className="h-auto w-full object-cover"
                />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
