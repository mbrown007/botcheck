import type { PackRunFailureCategory } from "@/lib/api/types";

export function packRunFailureCategoryLabel(
  value: PackRunFailureCategory | null | undefined
): string | null {
  if (!value) {
    return null;
  }
  if (value === "dispatch_error") {
    return "Dispatch Error";
  }
  if (value === "run_error") {
    return "Run Error";
  }
  if (value === "gate_blocked") {
    return "Gate Blocked";
  }
  return null;
}

export function packRunFailureCategoryTone(
  value: PackRunFailureCategory | null | undefined
): "text-fail" | "text-warn" | "text-text-muted" {
  if (value === "gate_blocked") {
    return "text-warn";
  }
  if (value === "dispatch_error" || value === "run_error") {
    return "text-fail";
  }
  return "text-text-muted";
}

