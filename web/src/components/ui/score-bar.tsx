import { cn } from "@/lib/utils";

interface ScoreBarProps {
  label: string;
  value: number; // 0–100
  className?: string;
}

function colorClass(value: number): string {
  if (value >= 80) return "bg-pass";
  if (value >= 50) return "bg-warn";
  return "bg-fail";
}

export function ScoreBar({ label, value, className }: ScoreBarProps) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className={cn("space-y-1", className)}>
      <div className="flex items-center justify-between text-xs text-text-secondary">
        <span>{label}</span>
        <span className="font-mono text-text-primary">{pct}%</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-bg-elevated overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", colorClass(pct))}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
