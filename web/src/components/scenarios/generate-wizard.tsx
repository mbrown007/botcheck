"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import {
  generateScenarios,
  uploadScenario,
  useGenerateJob,
  type GeneratedScenario,
} from "@/lib/api";

type WizardStep = 1 | 2 | 3 | "generating" | "results";

interface GenerateWizardProps {
  onClose: () => void;
}

interface SaveState {
  [index: number]: "idle" | "saving" | "saved" | "error";
}

function ScenarioPreviewCard({
  scenario,
  index,
  saveState,
  onSave,
}: {
  scenario: GeneratedScenario;
  index: number;
  saveState: "idle" | "saving" | "saved" | "error";
  onSave: (index: number) => void;
}) {
  // Extract first caller utterance from yaml as a preview quote
  const firstQuoteMatch = scenario.yaml.match(/text:\s*["']?([^"'\n]+)/);
  const firstQuote = firstQuoteMatch ? firstQuoteMatch[1].trim() : "";

  return (
    <div className="rounded-lg border border-border bg-bg-elevated p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium text-text-primary truncate">{scenario.name}</p>
          <div className="flex gap-2 mt-1 flex-wrap">
            <span className="text-xs px-1.5 py-0.5 rounded bg-bg-surface border border-border text-text-secondary">
              {scenario.type}
            </span>
            {scenario.technique && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-bg-surface border border-border text-brand">
                {scenario.technique}
              </span>
            )}
            <span className="text-xs text-text-muted">{scenario.turns} turns</span>
          </div>
        </div>
      </div>
      {firstQuote && (
        <p className="text-xs text-text-secondary italic border-l-2 border-border pl-2">
          &ldquo;{firstQuote}&rdquo;
        </p>
      )}
      <Button
        variant="secondary"
        size="sm"
        disabled={saveState === "saving" || saveState === "saved"}
        onClick={() => onSave(index)}
        className="self-start"
      >
        {saveState === "saving"
          ? "Saving…"
          : saveState === "saved"
          ? "Saved"
          : saveState === "error"
          ? "Retry Save"
          : "Save to Library"}
      </Button>
    </div>
  );
}

export function GenerateWizard({ onClose }: GenerateWizardProps) {
  const [step, setStep] = useState<WizardStep>(1);
  const [targetPrompt, setTargetPrompt] = useState("");
  const [steeringPrompt, setSteeringPrompt] = useState("");
  const [objective, setObjective] = useState("");
  const [count, setCount] = useState(3);
  const [jobId, setJobId] = useState<string | null>(null);
  const [launchError, setLaunchError] = useState("");
  const [saveStates, setSaveStates] = useState<SaveState>({});

  const { data: jobData } = useGenerateJob(jobId);

  // Transition from generating → results on terminal status
  const isTerminal =
    jobData?.status === "complete" ||
    jobData?.status === "partial" ||
    jobData?.status === "failed";

  const effectiveStep: WizardStep =
    step === "generating" && isTerminal ? "results" : step;

  const handleGenerate = useCallback(async () => {
    setLaunchError("");
    setStep("generating");
    try {
      const result = await generateScenarios({
        target_system_prompt: targetPrompt,
        steering_prompt: steeringPrompt,
        user_objective: objective,
        count,
      });
      setJobId(result.job_id);
    } catch (err) {
      setLaunchError(err instanceof Error ? err.message : "Failed to start generation");
      setStep(3);
    }
  }, [targetPrompt, steeringPrompt, objective, count]);

  const handleSave = useCallback(
    async (index: number) => {
      const scenario = jobData?.scenarios[index];
      if (!scenario) return;
      setSaveStates((prev) => ({ ...prev, [index]: "saving" }));
      try {
        await uploadScenario(scenario.yaml);
        setSaveStates((prev) => ({ ...prev, [index]: "saved" }));
      } catch {
        setSaveStates((prev) => ({ ...prev, [index]: "error" }));
      }
    },
    [jobData]
  );

  const handleReset = useCallback(() => {
    setStep(1);
    setTargetPrompt("");
    setSteeringPrompt("");
    setObjective("");
    setCount(3);
    setJobId(null);
    setLaunchError("");
    setSaveStates({});
  }, []);

  const estimatedSeconds = count * 8;

  return (
    <Dialog.Root open onOpenChange={(open) => { if (!open) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-overlay/60 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-bg-surface p-6 shadow-xl">
          <Dialog.Title className="mb-1 text-base font-semibold text-text-primary">
            AI Scenario Generator
          </Dialog.Title>
          <Dialog.Description className="mb-5 text-sm text-text-secondary">
            Red-team a bot&rsquo;s system prompt to auto-generate diverse adversarial test scenarios.
          </Dialog.Description>

          {/* Step 1: Target system prompt */}
          {effectiveStep === 1 && (
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-text-secondary mb-1">
                  Generation steering{" "}
                  <span className="font-normal text-text-muted">(optional)</span>
                </label>
                <textarea
                  value={steeringPrompt}
                  onChange={(e) => setSteeringPrompt(e.target.value)}
                  maxLength={2000}
                  rows={3}
                  className="w-full rounded-md border border-border bg-bg-elevated p-3 text-sm text-text-primary placeholder:text-text-muted focus:border-border-focus focus:outline-none resize-none"
                  placeholder="e.g. Focus on PII elicitation and auth bypass. Vary caller mood. Prefer multi-turn persistence attacks."
                  spellCheck={false}
                />
                <div className="flex justify-between mt-1">
                  <p className="text-xs text-text-muted">
                    Guides Claude on which attack surfaces, techniques, or tone to prioritise.
                  </p>
                  <span className="text-xs text-text-muted">{steeringPrompt.length}/2000</span>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-text-secondary mb-1">
                  Target bot system prompt
                </label>
                <textarea
                  value={targetPrompt}
                  onChange={(e) => setTargetPrompt(e.target.value)}
                  maxLength={8000}
                  className="h-44 w-full rounded-md border border-border bg-bg-elevated p-3 font-mono text-xs text-text-primary placeholder:text-text-muted focus:border-border-focus focus:outline-none resize-none"
                  placeholder="Paste the bot's system prompt here…"
                  spellCheck={false}
                />
                <div className="flex justify-between mt-1">
                  <p className="text-xs text-text-muted">
                    Not stored after generation — used only to craft scenarios.
                  </p>
                  <span className="text-xs text-text-muted">{targetPrompt.length}/8000</span>
                </div>
              </div>
              <div className="flex justify-end gap-3">
                <Dialog.Close asChild>
                  <Button variant="secondary">Cancel</Button>
                </Dialog.Close>
                <Button
                  variant="primary"
                  disabled={!targetPrompt.trim()}
                  onClick={() => setStep(2)}
                >
                  Next
                </Button>
              </div>
            </div>
          )}

          {/* Step 2: Objective */}
          {effectiveStep === 2 && (
            <div className="space-y-4">
              <div>
                <label className="block text-xs text-text-secondary mb-1.5">
                  Test objective
                </label>
                <input
                  type="text"
                  value={objective}
                  onChange={(e) => setObjective(e.target.value)}
                  maxLength={500}
                  className="w-full rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-border-focus focus:outline-none"
                  placeholder="e.g. Probe jailbreak resistance and policy boundaries"
                />
                <p className="text-xs text-text-muted mt-1">{objective.length}/500</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary mb-2">Coverage areas (optional — guides scenario diversity)</p>
                <div className="flex flex-wrap gap-3">
                  {(["routing", "policy", "jailbreak", "PII handling"] as const).map((area) => (
                    <label key={area} className="flex items-center gap-1.5 cursor-pointer">
                      <input
                        type="checkbox"
                        className="accent-brand"
                        onChange={(e) => {
                          if (e.target.checked) {
                            setObjective((prev) =>
                              prev ? `${prev}, ${area}` : area
                            );
                          }
                        }}
                      />
                      <span className="text-xs text-text-primary">{area}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="flex justify-between gap-3">
                <Button variant="secondary" onClick={() => setStep(1)}>
                  Back
                </Button>
                <Button
                  variant="primary"
                  disabled={!objective.trim()}
                  onClick={() => setStep(3)}
                >
                  Next
                </Button>
              </div>
            </div>
          )}

          {/* Step 3: Count & Generate */}
          {effectiveStep === 3 && (
            <div className="space-y-4">
              <div>
                <label className="block text-xs text-text-secondary mb-1.5">
                  Number of scenarios to generate (1–10)
                </label>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={count}
                  onChange={(e) =>
                    setCount(Math.min(10, Math.max(1, Number(e.target.value))))
                  }
                  className="w-32 rounded-md border border-border bg-bg-elevated px-3 py-2 text-sm text-text-primary focus:border-border-focus focus:outline-none"
                />
                <p className="text-xs text-text-muted mt-1">
                  Estimated ~{estimatedSeconds}s
                </p>
              </div>
              {launchError && (
                <p className="text-xs text-fail">{launchError}</p>
              )}
              <div className="flex justify-between gap-3">
                <Button variant="secondary" onClick={() => setStep(2)}>
                  Back
                </Button>
                <Button variant="primary" onClick={() => void handleGenerate()}>
                  Generate {count} scenario{count !== 1 ? "s" : ""}
                </Button>
              </div>
            </div>
          )}

          {/* Generating: spinner */}
          {effectiveStep === "generating" && (
            <div className="flex flex-col items-center gap-4 py-8">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-border border-t-brand" />
              <p className="text-sm text-text-secondary">
                Generating {count} scenario{count !== 1 ? "s" : ""}…
              </p>
              {jobData?.status === "running" && (
                <p className="text-xs text-text-muted">Claude is crafting adversarial scenarios</p>
              )}
            </div>
          )}

          {/* Results */}
          {effectiveStep === "results" && jobData && (
            <div className="space-y-4">
              <p className="text-sm text-text-secondary">
                {jobData.status === "failed" ? (
                  <span className="text-fail">Generation failed.</span>
                ) : (
                  <>
                    <span className="text-pass font-medium">
                      {jobData.count_succeeded} of {jobData.count_requested}
                    </span>{" "}
                    scenario{jobData.count_succeeded !== 1 ? "s" : ""} generated
                    {jobData.count_succeeded < jobData.count_requested &&
                      ` (${jobData.count_requested - jobData.count_succeeded} failed validation)`}
                  </>
                )}
              </p>

              {jobData.scenarios.length > 0 && (
                <div className="grid gap-3 max-h-96 overflow-y-auto pr-1">
                  {jobData.scenarios.map((scenario, i) => (
                    <ScenarioPreviewCard
                      key={i}
                      scenario={scenario}
                      index={i}
                      saveState={saveStates[i] ?? "idle"}
                      onSave={() => void handleSave(i)}
                    />
                  ))}
                </div>
              )}

              {jobData.errors.length > 0 && (
                <div className="rounded-md border border-fail-border bg-fail-bg p-3">
                  <p className="text-xs font-medium text-fail mb-1">Errors</p>
                  <ul className="space-y-1">
                    {jobData.errors.map((err, i) => (
                      <li key={i} className="text-xs text-fail">
                        {err}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="flex justify-between gap-3">
                <Button variant="secondary" onClick={handleReset}>
                  Generate More
                </Button>
                <Dialog.Close asChild>
                  <Button variant="primary" onClick={onClose}>
                    Close
                  </Button>
                </Dialog.Close>
              </div>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
