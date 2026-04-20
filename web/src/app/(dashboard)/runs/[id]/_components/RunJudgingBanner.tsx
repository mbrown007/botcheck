"use client";

export function RunJudgingBanner({ visible }: { visible: boolean }) {
  if (!visible) {
    return null;
  }

  return (
    <div className="flex items-center gap-3 rounded-lg border border-warn-border bg-warn-bg px-4 py-3">
      <svg
        className="h-4 w-4 animate-spin text-warn"
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
      >
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
      </svg>
      <span className="text-sm text-warn">Judging in progress — polling every 3s</span>
    </div>
  );
}
