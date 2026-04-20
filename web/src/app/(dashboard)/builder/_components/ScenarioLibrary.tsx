"use client";

import { useScenarios } from "@/lib/api";
import { filterGraphScenarios } from "@/lib/builder-scenario-access";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ScenarioLibraryProps {
  open: boolean;
  onToggle: () => void;
  scenarioId: string | null;
  copyingScenarioId: string | null;
  onSelect: (id: string) => void;
  onCopy: (id: string) => void;
}

export function ScenarioLibrary({
  open,
  onToggle,
  scenarioId,
  copyingScenarioId,
  onSelect,
  onCopy,
}: ScenarioLibraryProps) {
  const { data: scenarioLibrary, error: scenarioLibraryError } = useScenarios();
  const graphScenarios = filterGraphScenarios(scenarioLibrary);

  const scenarioLibraryErrorMessage =
    scenarioLibraryError instanceof Error
      ? scenarioLibraryError.message
      : scenarioLibraryError
        ? String(scenarioLibraryError)
        : "";

  return (
    <div className="rounded-md border border-border bg-bg-elevated">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
      >
        <h2 className="text-sm font-semibold text-text-primary">Scenario Library</h2>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-text-muted">
            {graphScenarios.length} total
          </span>
          <span className="text-xs text-text-muted">{open ? "▾" : "▸"}</span>
        </div>
      </button>
      {open && (
        <div className="border-t border-border px-3 pb-3">
          {scenarioLibraryErrorMessage && (
            <p className="mt-2 text-xs text-fail">
              Failed to load scenarios: {scenarioLibraryErrorMessage}
            </p>
          )}
          {!scenarioLibrary && !scenarioLibraryError && (
            <p className="mt-2 text-xs text-text-muted">Loading scenarios…</p>
          )}
          {graphScenarios.length > 0 && (
            <div className="mt-2 max-h-44 space-y-1 overflow-y-auto pr-1">
              {graphScenarios.map((scenario) => {
                const active = scenario.id === scenarioId;
                return (
                  <div
                    key={scenario.id}
                    className={cn(
                      "group w-full rounded-md border px-2 py-1.5 text-left",
                      active
                        ? "border-brand bg-brand-muted/40"
                        : "border-border bg-bg-surface hover:border-border-focus"
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-xs font-medium text-text-primary">
                        {scenario.name}
                      </span>
                      <span className="font-mono text-[10px] text-text-muted">
                        {scenario.type}
                      </span>
                    </div>
                    <p className="mt-0.5 truncate font-mono text-[10px] text-text-muted">
                      {scenario.id}
                    </p>
                    <div
                      className={cn(
                        "mt-2 flex gap-1 transition-opacity",
                        active
                          ? "opacity-100"
                          : "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"
                      )}
                    >
                      <Button
                        variant="secondary"
                        size="sm"
                        className="h-6 px-2 text-[10px]"
                        data-testid={`scenario-library-open-${scenario.id}`}
                        onClick={() => onSelect(scenario.id)}
                      >
                        Open
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        className="h-6 px-2 text-[10px]"
                        data-testid={`scenario-library-copy-${scenario.id}`}
                        disabled={copyingScenarioId === scenario.id}
                        onClick={() => onCopy(scenario.id)}
                      >
                        {copyingScenarioId === scenario.id ? "Copying…" : "Copy"}
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
