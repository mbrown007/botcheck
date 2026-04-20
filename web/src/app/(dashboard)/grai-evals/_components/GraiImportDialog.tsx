"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useState } from "react";
import { X } from "lucide-react";

import { Button } from "@/components/ui/button";

export function GraiImportDialog({
  open,
  importing,
  error,
  onOpenChange,
  onSubmit,
}: {
  open: boolean;
  importing: boolean;
  error: string;
  onOpenChange: (open: boolean) => void;
  onSubmit: (values: { name: string; yaml: string }) => Promise<void> | void;
}) {
  const [name, setName] = useState("");
  const [yaml, setYaml] = useState("");

  useEffect(() => {
    if (!open) {
      setName("");
      setYaml("");
    }
  }, [open]);

  async function handleSubmit() {
    await onSubmit({ name, yaml });
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-overlay/60 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(92vw,64rem)] max-h-[88vh] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl border border-border bg-bg-surface p-6 shadow-xl">
          <div className="flex items-start justify-between gap-4">
            <div>
              <Dialog.Title className="text-lg font-semibold text-text-primary">
                Import Promptfoo YAML
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-text-secondary">
                Conversion-first import. Unsupported promptfoo features return diagnostics instead of
                partially executing hidden runtime semantics.
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button variant="secondary" size="icon" aria-label="Close grai import dialog">
                <X className="h-4 w-4" />
              </Button>
            </Dialog.Close>
          </div>

          <div className="mt-6 grid gap-4">
            <label className="block">
              <span className="mb-1.5 block text-xs uppercase tracking-[0.16em] text-text-muted">
                Name Override
              </span>
              <input
                data-testid="grai-import-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Optional suite name override"
                className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-xs uppercase tracking-[0.16em] text-text-muted">
                Promptfoo YAML
              </span>
              <textarea
                data-testid="grai-import-yaml"
                value={yaml}
                onChange={(event) => setYaml(event.target.value)}
                rows={18}
                placeholder={"description: Billing smoke\nprompts:\n  - raw: Answer clearly: {{question}}\ntests:\n  - vars:\n      question: What is the refund policy?\n    assert:\n      - type: contains\n        value: refund"}
                className="w-full rounded-md border border-border bg-bg-elevated px-3 py-3 font-mono text-xs text-text-primary focus:border-border-focus focus:outline-none"
              />
            </label>
            <div className="rounded-xl border border-border bg-bg-elevated/70 px-4 py-3 text-xs text-text-secondary">
              First pass supports deterministic and Claude-backed assertion types from the Phase 32
              allowlist. Includes, hooks, plugin runtime semantics, and custom providers are rejected
              during import.
            </div>
            {error ? <p className="text-sm text-fail">{error}</p> : null}
          </div>

          <div className="mt-6 flex items-center justify-end gap-2">
            <Dialog.Close asChild>
              <Button variant="secondary">Cancel</Button>
            </Dialog.Close>
            <Button
              data-testid="grai-import-submit"
              onClick={() => void handleSubmit()}
              disabled={importing || !yaml.trim()}
            >
              {importing ? "Importing…" : "Import Suite"}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
