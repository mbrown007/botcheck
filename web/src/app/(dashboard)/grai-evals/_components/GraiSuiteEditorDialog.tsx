"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useState } from "react";
import { Plus, Trash2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { GraiEvalSuiteDetail, GraiEvalSuiteUpsertRequest } from "@/lib/api";

type PromptDraft = {
  label: string;
  prompt_text: string;
};

type CaseDraft = {
  description: string;
  variableName: string;
  variableValue: string;
  assertionType: string;
  assertionValue: string;
  threshold: string;
  tags: string;
};

const DEFAULT_PROMPT: PromptDraft = {
  label: "helpful",
  prompt_text: "Answer the user question clearly: {{question}}",
};

const DEFAULT_CASE: CaseDraft = {
  description: "Refund policy",
  variableName: "question",
  variableValue: "What is the refund policy?",
  assertionType: "contains",
  assertionValue: "refund",
  threshold: "0.8",
  tags: "billing, smoke-test",
};

function suiteToPromptDrafts(suite: GraiEvalSuiteDetail): PromptDraft[] {
  return suite.prompts.map((p) => ({ label: p.label, prompt_text: p.prompt_text }));
}

function suiteToCaseDrafts(suite: GraiEvalSuiteDetail): CaseDraft[] {
  return suite.cases.map((c) => {
    const firstAssertion = c.assert_json[0];
    const firstVarEntry = Object.entries(c.vars_json ?? {})[0];
    return {
      description: c.description ?? "",
      variableName: firstVarEntry?.[0] ?? "",
      variableValue: String(firstVarEntry?.[1] ?? ""),
      assertionType: firstAssertion?.assertion_type ?? "contains",
      assertionValue: firstAssertion?.raw_value ?? "",
      threshold: firstAssertion?.threshold != null ? String(firstAssertion.threshold) : "",
      tags: (c.tags_json ?? []).join(", "),
    };
  });
}

export function GraiSuiteEditorDialog({
  open,
  saving,
  deleting,
  error,
  initialSuite,
  onOpenChange,
  onSubmit,
  onDelete,
}: {
  open: boolean;
  saving: boolean;
  deleting?: boolean;
  error: string;
  initialSuite?: GraiEvalSuiteDetail | null;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: GraiEvalSuiteUpsertRequest) => Promise<void> | void;
  onDelete?: () => Promise<void> | void;
}) {
  const isEdit = !!initialSuite;

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [prompts, setPrompts] = useState<PromptDraft[]>([DEFAULT_PROMPT]);
  const [cases, setCases] = useState<CaseDraft[]>([DEFAULT_CASE]);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (!open) {
      setName("");
      setDescription("");
      setPrompts([DEFAULT_PROMPT]);
      setCases([DEFAULT_CASE]);
      setConfirmDelete(false);
      return;
    }
    if (initialSuite) {
      setName(initialSuite.name);
      setDescription(initialSuite.description ?? "");
      setPrompts(suiteToPromptDrafts(initialSuite));
      setCases(suiteToCaseDrafts(initialSuite));
    }
  }, [open, initialSuite]);

  function updatePrompt(index: number, patch: Partial<PromptDraft>) {
    setPrompts((current) => current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  }

  function updateCase(index: number, patch: Partial<CaseDraft>) {
    setCases((current) => current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  }

  async function handleSubmit() {
    const payload: GraiEvalSuiteUpsertRequest = {
      name,
      description: description.trim() || null,
      prompts: prompts.map((prompt) => ({
        label: prompt.label.trim(),
        prompt_text: prompt.prompt_text,
        metadata_json: {},
      })),
      cases: cases.map((row) => ({
        description: row.description.trim() || null,
        vars_json: row.variableName.trim()
          ? { [row.variableName.trim()]: row.variableValue }
          : {},
        assert_json: [
          {
            assertion_type: row.assertionType.trim(),
            raw_value: row.assertionValue.trim() || null,
            threshold: row.threshold.trim() ? Number(row.threshold) : null,
            weight: 1,
          },
        ],
        tags_json: row.tags
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        metadata_json: {},
        import_threshold: row.threshold.trim() ? Number(row.threshold) : null,
      })),
      metadata_json: {},
    };
    await onSubmit(payload);
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-overlay/60 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(94vw,76rem)] max-h-[88vh] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl border border-border bg-bg-surface p-6 shadow-xl">
          <div className="flex items-start justify-between gap-4">
            <div>
              <Dialog.Title className="text-lg font-semibold text-text-primary">
                {isEdit ? "Edit Eval Suite" : "Create Grai Eval Suite"}
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-text-secondary">
                {isEdit
                  ? "Update prompts, cases, and metadata. Existing run history is preserved."
                  : "Native BotCheck suite authoring for large direct-HTTP eval runs. Start small, then import promptfoo YAML when you need bulk conversion."}
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button variant="secondary" size="icon" aria-label="Close grai suite dialog">
                <X className="h-4 w-4" />
              </Button>
            </Dialog.Close>
          </div>

          <div className="mt-6 grid gap-6">
            <div className="grid gap-4 md:grid-cols-2">
              <label className="block">
                <span className="mb-1.5 block text-xs uppercase tracking-[0.16em] text-text-muted">
                  Suite Name
                </span>
                <input
                  data-testid="grai-suite-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Billing regression suite"
                  className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-xs uppercase tracking-[0.16em] text-text-muted">
                  Description
                </span>
                <input
                  data-testid="grai-suite-description"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="Validate common billing support paths."
                  className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                />
              </label>
            </div>

            <section className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-text-primary">Prompt Variants</h3>
                  <p className="text-xs text-text-muted">Each prompt variant is crossed with every test case.</p>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setPrompts((current) => [...current, { ...DEFAULT_PROMPT, label: `prompt-${current.length + 1}` }])}
                >
                  <Plus className="h-3.5 w-3.5" />
                  Add Prompt
                </Button>
              </div>
              <div className="grid gap-3">
                {prompts.map((prompt, index) => (
                  <div key={`prompt-${index}`} className="rounded-xl border border-border bg-bg-elevated/60 p-4">
                    <div className="grid gap-3 md:grid-cols-[220px_minmax(0,1fr)_auto]">
                      <input
                        data-testid={`grai-prompt-label-${index}`}
                        value={prompt.label}
                        onChange={(event) => updatePrompt(index, { label: event.target.value })}
                        placeholder="helpful"
                        className="rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                      />
                      <input
                        data-testid={`grai-prompt-text-${index}`}
                        value={prompt.prompt_text}
                        onChange={(event) => updatePrompt(index, { prompt_text: event.target.value })}
                        placeholder="Answer the user question clearly: {{question}}"
                        className="rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setPrompts((current) => current.length > 1 ? current.filter((_, itemIndex) => itemIndex !== index) : current)}
                        disabled={prompts.length === 1}
                        aria-label={`Remove prompt ${index + 1}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-text-primary">Test Cases</h3>
                  <p className="text-xs text-text-muted">Each case contributes variables, tags, and one first-pass assertion row.</p>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setCases((current) => [...current, { ...DEFAULT_CASE }])}
                >
                  <Plus className="h-3.5 w-3.5" />
                  Add Case
                </Button>
              </div>
              <div className="grid gap-3">
                {cases.map((row, index) => (
                  <div key={`case-${index}`} className="rounded-xl border border-border bg-bg-elevated/60 p-4">
                    <div className="mb-3 flex items-center justify-between">
                      <p className="text-xs uppercase tracking-[0.16em] text-text-muted">Case {index + 1}</p>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setCases((current) => current.length > 1 ? current.filter((_, itemIndex) => itemIndex !== index) : current)}
                        disabled={cases.length === 1}
                        aria-label={`Remove case ${index + 1}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                      <input
                        data-testid={`grai-case-description-${index}`}
                        value={row.description}
                        onChange={(event) => updateCase(index, { description: event.target.value })}
                        placeholder="Refund policy"
                        className="rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                      />
                      <input
                        data-testid={`grai-case-tags-${index}`}
                        value={row.tags}
                        onChange={(event) => updateCase(index, { tags: event.target.value })}
                        placeholder="billing, smoke-test"
                        className="rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                      />
                      <input
                        data-testid={`grai-case-var-name-${index}`}
                        value={row.variableName}
                        onChange={(event) => updateCase(index, { variableName: event.target.value })}
                        placeholder="question"
                        className="rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                      />
                      <input
                        data-testid={`grai-case-var-value-${index}`}
                        value={row.variableValue}
                        onChange={(event) => updateCase(index, { variableValue: event.target.value })}
                        placeholder="What is the refund policy?"
                        className="rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                      />
                      <input
                        data-testid={`grai-case-assertion-type-${index}`}
                        value={row.assertionType}
                        onChange={(event) => updateCase(index, { assertionType: event.target.value })}
                        placeholder="contains"
                        className="rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                      />
                      <input
                        data-testid={`grai-case-assertion-value-${index}`}
                        value={row.assertionValue}
                        onChange={(event) => updateCase(index, { assertionValue: event.target.value })}
                        placeholder="refund"
                        className="rounded-md border border-border bg-bg-surface px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                      />
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {error ? <p className="text-sm text-fail">{error}</p> : null}
          </div>

          <div className="mt-6 flex items-center justify-between gap-2">
            {isEdit && onDelete ? (
              <div className="flex items-center gap-2">
                {confirmDelete ? (
                  <>
                    <span className="text-xs text-text-secondary">Delete this suite?</span>
                    <Button
                      data-testid="grai-suite-delete-confirm"
                      variant="destructive"
                      size="sm"
                      onClick={() => void onDelete()}
                      disabled={deleting}
                    >
                      {deleting ? "Deleting…" : "Yes, delete"}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setConfirmDelete(false)}
                      disabled={deleting}
                    >
                      Cancel
                    </Button>
                  </>
                ) : (
                  <Button
                    data-testid="grai-suite-delete"
                    variant="ghost"
                    size="sm"
                    className="text-fail hover:bg-fail-bg/40 hover:text-fail"
                    onClick={() => setConfirmDelete(true)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Delete Suite
                  </Button>
                )}
              </div>
            ) : (
              <div />
            )}
            <div className="flex items-center gap-2">
              <Dialog.Close asChild>
                <Button variant="secondary">Cancel</Button>
              </Dialog.Close>
              <Button
                data-testid="grai-suite-submit"
                onClick={() => void handleSubmit()}
                disabled={saving || !name.trim()}
              >
                {saving ? (isEdit ? "Saving…" : "Creating…") : (isEdit ? "Save Changes" : "Create Suite")}
              </Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
