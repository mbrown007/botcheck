import React from "react";
import { namespaceSegments, normalizeNamespace } from "@/lib/namespace-context";

export function NamespacePath({
  namespace,
  showUnscoped = true,
  compact = false,
}: {
  namespace?: string | null;
  showUnscoped?: boolean;
  compact?: boolean;
}) {
  const normalized = normalizeNamespace(namespace);
  const segments = namespaceSegments(namespace);

  if (!normalized) {
    if (!showUnscoped) {
      return null;
    }
    return (
      <span
        className={`inline-flex items-center rounded-full border border-dashed border-border px-2 py-0.5 text-text-muted ${
          compact ? "text-[10px]" : "text-[11px]"
        }`}
      >
        Unscoped
      </span>
    );
  }

  return (
    <span className="inline-flex flex-wrap items-center gap-1 text-text-muted">
      {segments.map((segment, index) => (
        <span key={`${normalized}-${segment}-${index}`} className="inline-flex items-center gap-1">
          {index > 0 ? <span className={compact ? "text-[10px]" : "text-[11px]"}>/</span> : null}
          <span
            className={`inline-flex items-center rounded-full border border-border bg-bg-elevated px-2 py-0.5 ${
              compact ? "text-[10px]" : "text-[11px]"
            }`}
          >
            {segment}
          </span>
        </span>
      ))}
    </span>
  );
}
