import React from "react";
import { cn } from "@/lib/utils";

const variantMap: Record<string, string> = {
  pass: "bg-pass-bg border border-pass-border text-pass",
  fail: "bg-fail-bg border border-fail-border text-fail",
  warn: "bg-warn-bg border border-warn-border text-warn",
  info: "bg-info-bg border border-info-border text-info",
  pending: "bg-bg-elevated border border-border text-text-secondary",
};

function resolveVariant(value?: string | null): string {
  if (!value) return variantMap.pending;
  const v = value.toLowerCase();
  if (v === "passed" || v === "pass" || v === "complete") return variantMap.pass;
  if (v === "blocked" || v === "fail" || v === "failed") return variantMap.fail;
  if (v === "judging" || v === "running" || v === "warn") return variantMap.warn;
  if (v === "pending") return variantMap.pending;
  if (v === "info") return variantMap.info;
  return variantMap.pending;
}

interface StatusBadgeProps {
  value?: string | null;
  label?: string;
  className?: string;
}

export function StatusBadge({ value, label, className }: StatusBadgeProps) {
  const display = label ?? value ?? "—";
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-medium uppercase tracking-wide",
        resolveVariant(value),
        className
      )}
    >
      {display}
    </span>
  );
}
