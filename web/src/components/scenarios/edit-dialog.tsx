"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { type KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  getScenarioSource,
  updateScenario,
  validateScenarioYaml,
  type ScenarioValidationResult,
} from "@/lib/api";

interface ScenarioEditDialogProps {
  scenarioId: string | null;
  onClose: () => void;
  onSuccess?: () => void;
}

interface BranchingCompletion {
  label: string;
  insertText: string;
  description: string;
}

const BRANCHING_COMPLETIONS: BranchingCompletion[] = [
  {
    label: "branching",
    insertText:
      'branching:\n  cases:\n    - condition: ""\n      next: ""\n  default: ""',
    description: "Branch selector block for a turn.",
  },
  {
    label: "cases",
    insertText: 'cases:\n  - condition: ""\n    next: ""',
    description: "Branching condition list.",
  },
  {
    label: "condition",
    insertText: 'condition: ""',
    description: "Natural-language condition text for classifier matching.",
  },
  {
    label: "next",
    insertText: 'next: ""',
    description: "Target turn id for this edge.",
  },
  {
    label: "default",
    insertText: 'default: ""',
    description: "Fallback target when no case matches.",
  },
  {
    label: "max_visits",
    insertText: "max_visits: 1",
    description: "Per-turn loop guard cap (0 means unlimited).",
  },
];

function computeBranchingCompletions(yaml: string, cursor: number | null): {
  prefixStart: number;
  prefixEnd: number;
  suggestions: BranchingCompletion[];
} {
  if (cursor === null || cursor <= 0 || cursor > yaml.length) {
    return { prefixStart: 0, prefixEnd: 0, suggestions: [] };
  }
  const beforeCursor = yaml.slice(0, cursor);
  const match = beforeCursor.match(/([a-z_]+)$/i);
  if (!match) {
    return { prefixStart: cursor, prefixEnd: cursor, suggestions: [] };
  }
  const prefix = match[1].toLowerCase();
  const prefixStart = cursor - prefix.length;
  const suggestions = BRANCHING_COMPLETIONS.filter((item) =>
    item.label.startsWith(prefix)
  );
  return {
    prefixStart,
    prefixEnd: cursor,
    suggestions,
  };
}

export function ScenarioEditDialog({
  scenarioId,
  onClose,
  onSuccess,
}: ScenarioEditDialogProps) {
  const [yaml, setYaml] = useState("");
  const [status, setStatus] = useState<
    "idle" | "loading" | "validating" | "saving" | "error"
  >("idle");
  const [validation, setValidation] = useState<ScenarioValidationResult | null>(null);
  const [validationError, setValidationError] = useState("");
  const [error, setError] = useState("");
  const [completionPrefixStart, setCompletionPrefixStart] = useState(0);
  const [completionPrefixEnd, setCompletionPrefixEnd] = useState(0);
  const [completionSuggestions, setCompletionSuggestions] = useState<
    BranchingCompletion[]
  >([]);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const validateReq = useRef(0);

  const refreshCompletions = useCallback((value: string, cursor: number | null) => {
    const next = computeBranchingCompletions(value, cursor);
    setCompletionPrefixStart(next.prefixStart);
    setCompletionPrefixEnd(next.prefixEnd);
    setCompletionSuggestions(next.suggestions);
  }, []);

  const runValidation = useCallback(async (inputYaml: string) => {
    const trimmed = inputYaml.trim();
    if (!trimmed) {
      setValidation(null);
      setValidationError("");
      setStatus("idle");
      return null;
    }

    setStatus("validating");
    setValidationError("");
    const reqId = ++validateReq.current;

    try {
      const result = await validateScenarioYaml(trimmed);
      if (validateReq.current === reqId) {
        setValidation(result);
        setStatus("idle");
      }
      return result;
    } catch (err) {
      if (validateReq.current === reqId) {
        setValidation(null);
        setValidationError(err instanceof Error ? err.message : "Validation failed");
        setStatus("idle");
      }
      return null;
    }
  }, []);

  useEffect(() => {
    if (!scenarioId) {
      return;
    }

    let cancelled = false;
    setStatus("loading");
    setError("");
    setValidation(null);
    setValidationError("");

    getScenarioSource(scenarioId)
      .then((payload) => {
        if (cancelled) {
          return;
        }
        setYaml(payload.yaml_content);
        setStatus("idle");
        void runValidation(payload.yaml_content);
      })
      .catch((err) => {
        if (cancelled) {
          return;
        }
        setError(err instanceof Error ? err.message : "Failed to load scenario source");
        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [scenarioId, runValidation]);

  useEffect(() => {
    if (!scenarioId || !yaml.trim()) {
      return;
    }
    const handle = setTimeout(() => {
      void runValidation(yaml);
    }, 400);
    return () => clearTimeout(handle);
  }, [scenarioId, yaml, runValidation]);

  const handleSave = useCallback(async () => {
    if (!scenarioId || !yaml.trim()) {
      return;
    }

    const latestValidation = await runValidation(yaml);
    if (!latestValidation?.valid) {
      setError("Fix validation errors before saving.");
      return;
    }

    setStatus("saving");
    setError("");
    try {
      await updateScenario(scenarioId, yaml);
      onSuccess?.();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
      setStatus("error");
    }
  }, [onClose, onSuccess, runValidation, scenarioId, yaml]);

  const applyCompletion = useCallback(
    (completion: BranchingCompletion) => {
      const nextYaml = `${yaml.slice(0, completionPrefixStart)}${completion.insertText}${yaml.slice(
        completionPrefixEnd
      )}`;
      const nextCursor = completionPrefixStart + completion.insertText.length;
      setYaml(nextYaml);
      requestAnimationFrame(() => {
        if (!textareaRef.current) {
          return;
        }
        textareaRef.current.focus();
        textareaRef.current.setSelectionRange(nextCursor, nextCursor);
        refreshCompletions(nextYaml, nextCursor);
      });
    },
    [completionPrefixEnd, completionPrefixStart, refreshCompletions, yaml]
  );

  const handleEditorChange = useCallback(
    (value: string, cursor: number | null) => {
      setYaml(value);
      refreshCompletions(value, cursor);
    },
    [refreshCompletions]
  );

  const handleEditorCursorRefresh = useCallback(() => {
    if (!textareaRef.current) {
      return;
    }
    refreshCompletions(yaml, textareaRef.current.selectionStart);
  }, [refreshCompletions, yaml]);

  const handleEditorKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === "Tab" && completionSuggestions.length > 0) {
        event.preventDefault();
        applyCompletion(completionSuggestions[0]);
      }
    },
    [applyCompletion, completionSuggestions]
  );

  return (
    <Dialog.Root
      open={scenarioId !== null}
      onOpenChange={(open) => {
        if (!open) {
          setYaml("");
          setValidation(null);
          setValidationError("");
          setError("");
          setStatus("idle");
          setCompletionPrefixStart(0);
          setCompletionPrefixEnd(0);
          setCompletionSuggestions([]);
          onClose();
        }
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-overlay/60 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-3xl -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-bg-surface p-6 shadow-xl">
          <Dialog.Title className="mb-1 text-base font-semibold text-text-primary">
            Edit Scenario
          </Dialog.Title>
          <Dialog.Description className="mb-4 text-sm text-text-secondary">
            Update existing scenario YAML and save a new version hash.
          </Dialog.Description>

          <textarea
            ref={textareaRef}
            value={yaml}
            onChange={(e) =>
              handleEditorChange(e.target.value, e.currentTarget.selectionStart)
            }
            onClick={handleEditorCursorRefresh}
            onKeyUp={handleEditorCursorRefresh}
            onKeyDown={handleEditorKeyDown}
            className="h-72 w-full resize-none rounded-md border border-border bg-[#0F172A] p-3 font-mono text-[13px] leading-5 text-[#E2E8F0] placeholder:text-[#94A3B8] focus:border-border-focus focus:outline-none"
            placeholder={status === "loading" ? "Loading scenario YAML..." : "Edit YAML..."}
            spellCheck={false}
            disabled={status === "loading" || status === "saving"}
            style={{ colorScheme: "dark" }}
          />

          {completionSuggestions.length > 0 && (
            <div className="mt-2 rounded-md border border-border bg-bg-elevated p-2">
              <p className="mb-2 text-[11px] uppercase tracking-wide text-text-muted">
                Branching Autocomplete (Tab to insert)
              </p>
              <div className="flex flex-wrap gap-2">
                {completionSuggestions.map((completion) => (
                  <button
                    key={completion.label}
                    type="button"
                    onClick={() => applyCompletion(completion)}
                    className="rounded border border-border bg-bg-surface px-2 py-1 text-left text-[11px] font-mono text-text-secondary hover:border-border-focus hover:text-text-primary"
                    title={completion.description}
                  >
                    {completion.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="mt-2 flex items-center justify-between">
            <div className="text-xs">
              {status === "loading" && <span className="text-warn">Loading…</span>}
              {status === "validating" && <span className="text-warn">Validating…</span>}
              {validation?.valid && (
                <span className="text-pass">
                  Valid scenario: {validation.scenario_id} ({validation.turns} turns)
                </span>
              )}
              {!validation?.valid && validation && (
                <span className="text-fail">
                  {validation.errors.length} validation issue
                  {validation.errors.length === 1 ? "" : "s"}
                </span>
              )}
            </div>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void runValidation(yaml)}
              disabled={
                status === "loading" ||
                status === "saving" ||
                status === "validating" ||
                !yaml.trim()
              }
            >
              Validate
            </Button>
          </div>

          {validationError && <p className="mt-2 text-xs text-fail">{validationError}</p>}

          {validation && !validation.valid && validation.errors.length > 0 && (
            <div className="mt-3 max-h-36 overflow-y-auto rounded-md border border-fail-border bg-fail-bg p-2">
              <p className="mb-1 text-xs font-medium text-fail">Validation Errors</p>
              <ul className="space-y-1">
                {validation.errors.map((item, i) => (
                  <li key={`${item.field}:${i}`} className="text-xs text-fail">
                    <span className="font-mono">{item.field}</span>: {item.message}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {validation?.valid && validation.path_summary && (
            <div className="mt-3 rounded-md border border-border bg-bg-elevated p-3">
              <p className="mb-2 text-xs font-medium text-text-secondary">
                ASCII Path Summary (read-only)
              </p>
              <pre className="max-h-52 overflow-y-auto whitespace-pre-wrap font-mono text-xs text-text-primary">
                {validation.path_summary}
              </pre>
            </div>
          )}

          {error && <p className="mt-2 text-xs text-fail">{error}</p>}

          <div className="mt-4 flex justify-end gap-3">
            <Dialog.Close asChild>
              <Button variant="secondary">Cancel</Button>
            </Dialog.Close>
            <Button
              variant="primary"
              onClick={handleSave}
              disabled={
                status === "loading" ||
                status === "saving" ||
                status === "validating" ||
                !yaml.trim() ||
                (!!validation && !validation.valid)
              }
            >
              {status === "saving" ? "Saving…" : "Save"}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
