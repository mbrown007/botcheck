"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useState } from "react";
import { LoaderCircle, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { getGraiEvalArtifact, mapApiError, type GraiEvalArtifactResponse } from "@/lib/api";

export function GraiArtifactDialog({
  open,
  evalRunId,
  evalResultId,
  onOpenChange,
}: {
  open: boolean;
  evalRunId: string | null;
  evalResultId: string | null;
  onOpenChange: (open: boolean) => void;
}) {
  const [artifact, setArtifact] = useState<GraiEvalArtifactResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open || !evalRunId || !evalResultId) {
      setArtifact(null);
      setLoading(false);
      setError("");
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    void getGraiEvalArtifact(evalRunId, evalResultId)
      .then((response) => {
        if (!cancelled) {
          setArtifact(response);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(mapApiError(err, "Failed to load grai eval artifact").message);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [evalResultId, evalRunId, open]);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-overlay/60 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(94vw,72rem)] max-h-[88vh] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl border border-border bg-bg-surface p-6 shadow-xl">
          <div className="flex items-start justify-between gap-4">
            <div>
              <Dialog.Title className="text-lg font-semibold text-text-primary">
                Exemplar Request / Response
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-text-secondary">
                Stored eval artifact for this prompt/case/assertion result.
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button variant="secondary" size="icon" aria-label="Close grai artifact dialog">
                <X className="h-4 w-4" />
              </Button>
            </Dialog.Close>
          </div>

          {loading ? (
            <div className="flex items-center gap-2 py-10 text-sm text-text-secondary">
              <LoaderCircle className="h-4 w-4 animate-spin" />
              Loading artifact…
            </div>
          ) : null}
          {error ? <p className="mt-6 text-sm text-fail">{error}</p> : null}
          {artifact ? (
            <div className="mt-6 grid gap-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-xl border border-border bg-bg-elevated/60 p-4">
                  <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Prompt</p>
                  <pre className="mt-3 whitespace-pre-wrap break-words text-sm text-text-primary">
                    {artifact.prompt_text}
                  </pre>
                </div>
                <div className="rounded-xl border border-border bg-bg-elevated/60 p-4">
                  <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Response</p>
                  <pre className="mt-3 whitespace-pre-wrap break-words text-sm text-text-primary">
                    {artifact.response_text}
                  </pre>
                </div>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-xl border border-border bg-bg-elevated/60 p-4">
                  <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Variables</p>
                  <pre className="mt-3 overflow-x-auto text-xs text-text-primary">
                    {JSON.stringify(artifact.vars_json, null, 2)}
                  </pre>
                </div>
                <div className="rounded-xl border border-border bg-bg-elevated/60 p-4">
                  <p className="text-[11px] uppercase tracking-[0.16em] text-text-muted">Assertions</p>
                  <pre className="mt-3 overflow-x-auto text-xs text-text-primary">
                    {JSON.stringify(artifact.assertions, null, 2)}
                  </pre>
                </div>
              </div>
            </div>
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
