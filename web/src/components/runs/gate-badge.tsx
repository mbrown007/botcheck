import { cn } from "@/lib/utils";

interface GateBadgeProps {
  result?: string | null;
  className?: string;
}

export function GateBadge({ result, className }: GateBadgeProps) {
  const isPassed = result === "passed";
  const isBlocked = result === "blocked";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-semibold uppercase tracking-widest border",
        isPassed && "bg-pass-bg border-pass-border text-pass",
        isBlocked && "bg-fail-bg border-fail-border text-fail",
        !isPassed && !isBlocked && "bg-bg-elevated border-border text-text-muted",
        className
      )}
    >
      {isPassed && <span className="h-1.5 w-1.5 rounded-full bg-pass" />}
      {isBlocked && <span className="h-1.5 w-1.5 rounded-full bg-fail" />}
      {result ? result.toUpperCase() : "PENDING"}
    </span>
  );
}
