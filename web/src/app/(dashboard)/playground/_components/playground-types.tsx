import { CheckCircle2, CircleDashed, CircleDot, CircleSlash2, XCircle } from "lucide-react";

export type ProgressStatus = "pending" | "active" | "passed" | "failed" | "skipped";

export function progressStatusClasses(status: ProgressStatus): string {
  switch (status) {
    case "active":
      return "border-brand/25 bg-brand/5";
    case "passed":
      return "border-pass/25 bg-pass/5";
    case "failed":
      return "border-fail-border bg-fail/5";
    case "skipped":
      return "border-border bg-bg-elevated/70 opacity-85";
    default:
      return "border-border bg-bg-elevated";
  }
}

export function progressStatusIcon(status: ProgressStatus) {
  switch (status) {
    case "active":
      return <CircleDot className="h-4 w-4 text-brand" />;
    case "passed":
      return <CheckCircle2 className="h-4 w-4 text-pass" />;
    case "failed":
      return <XCircle className="h-4 w-4 text-fail" />;
    case "skipped":
      return <CircleSlash2 className="h-4 w-4 text-text-muted" />;
    default:
      return <CircleDashed className="h-4 w-4 text-text-muted" />;
  }
}

export type TargetChoice =
  | { kind: "graph"; id: string }
  | { kind: "ai"; id: string }
  | null;

export function parseTargetValue(value: string): TargetChoice {
  const [kind, id] = value.split(":", 2);
  if (!id) {
    return null;
  }
  if (kind === "graph" || kind === "ai") {
    return { kind, id };
  }
  return null;
}

export function targetValueFromChoice(choice: TargetChoice): string {
  if (!choice) {
    return "";
  }
  return `${choice.kind}:${choice.id}`;
}
