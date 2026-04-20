import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";

export function ScheduleModalShell({
  title,
  subtitle,
  onClose,
  onSubmit,
  submitLabel,
  submitDisabled,
  error,
  children,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  onSubmit: () => void;
  submitLabel: string;
  submitDisabled: boolean;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-40 overflow-y-auto">
      <div className="absolute inset-0 bg-overlay/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-50 flex min-h-full items-start justify-center px-4 py-6 sm:px-6">
        <div className="flex max-h-[calc(100vh-3rem)] w-full max-w-2xl flex-col rounded-lg border border-border bg-bg-surface shadow-xl">
          <div className="border-b border-border px-6 py-4">
            <h2 className="text-base font-semibold text-text-primary">{title}</h2>
            {subtitle ? <p className="mt-1 font-mono text-xs text-text-muted">{subtitle}</p> : null}
          </div>
          <div className="min-h-0 overflow-y-auto px-6 py-5">
            {children}
            {error ? <p className="mt-3 text-xs text-fail">{error}</p> : null}
          </div>
          <div className="flex justify-end gap-3 border-t border-border px-6 py-4">
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button variant="primary" onClick={onSubmit} disabled={submitDisabled}>
              {submitLabel}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
