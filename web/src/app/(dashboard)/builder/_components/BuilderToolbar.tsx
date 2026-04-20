"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/badge";
import { cacheStatusVariant } from "@/lib/cache-status";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { ChevronDown, HelpCircle, Redo2, Undo2, Upload, Download, FilePlus } from "lucide-react";
import { useBuilderStore } from "@/lib/builder-store";

interface BuilderToolbarProps {
  scenarioId: string | null;
  loading: boolean;
  saveState: "idle" | "saving";
  canSave: boolean;
  cacheStatus?: string | null;
  cacheCoverage?: string | null;
  canRebuildCache?: boolean;
  rebuildingCache?: boolean;
  onSave: () => void;
  onBack: () => void;
  onApplyYaml: () => void;
  onExportYaml: () => void;
  onImportYaml: (file: File) => void;
  onNewScenario: () => void;
  onRebuildCache?: () => void;
}

export function BuilderToolbar({
  scenarioId,
  loading,
  saveState,
  canSave,
  cacheStatus,
  cacheCoverage,
  canRebuildCache = false,
  rebuildingCache = false,
  onSave,
  onBack,
  onApplyYaml,
  onExportYaml,
  onImportYaml,
  onNewScenario,
  onRebuildCache,
}: BuilderToolbarProps) {
  const meta = useBuilderStore((state) => state.meta);
  const isDirty = useBuilderStore((state) => state.isDirty);
  const canUndo = useBuilderStore((state) => state.canUndo);
  const canRedo = useBuilderStore((state) => state.canRedo);
  const undo = useBuilderStore((state) => state.undo);
  const redo = useBuilderStore((state) => state.redo);

  const importInputRef = useRef<HTMLInputElement | null>(null);
  const [fileMenuOpen, setFileMenuOpen] = useState(false);
  const [pendingNewDraft, setPendingNewDraft] = useState(false);

  useEffect(() => {
    if (!pendingNewDraft || fileMenuOpen) {
      return;
    }

    const timer = window.setTimeout(() => {
      setPendingNewDraft(false);
      onNewScenario();
    }, 250);
    return () => {
      window.clearTimeout(timer);
    };
  }, [fileMenuOpen, onNewScenario, pendingNewDraft]);

  const scenarioLabel =
    typeof meta.name === "string" && meta.name.trim() ? meta.name : scenarioId ?? "Draft";
  const namespaceLabel =
    typeof meta.namespace === "string" && meta.namespace.trim()
      ? meta.namespace.trim().replace(/^\/+|\/+$/g, "")
      : "";

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div>
        <button
          type="button"
          onClick={onBack}
          className="text-xs text-text-secondary hover:text-text-primary"
        >
          ← Back to Scenarios
        </button>
        <h1 className="mt-1 text-xl font-semibold text-text-primary">
          Scenario Builder{" "}
          {isDirty && <span className="text-brand" title="Unsaved changes">●</span>}
        </h1>
        {namespaceLabel ? (
          <p className="mt-1 text-[11px] uppercase tracking-[0.22em] text-text-muted">
            {namespaceLabel}
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm text-text-secondary">
            {scenarioLabel} {scenarioId ? `(${scenarioId})` : "(draft)"}
          </p>
          {scenarioId && cacheStatus && (
            <StatusBadge
              value={cacheStatusVariant(cacheStatus)}
              label={`cache:${cacheStatus}`}
            />
          )}
          {scenarioId && cacheCoverage && (
            <span className="text-xs text-text-muted">{cacheCoverage} turns cached</span>
          )}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {/* File group */}
        <input
          ref={importInputRef}
          type="file"
          accept=".yaml,.yml,text/yaml,text/x-yaml,application/x-yaml"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) {
              onImportYaml(file);
            }
            event.currentTarget.value = "";
          }}
        />
        <DropdownMenu open={fileMenuOpen} onOpenChange={setFileMenuOpen}>
          <DropdownMenuTrigger asChild>
            <Button variant="secondary" size="sm" disabled={saveState === "saving" || loading}>
              File <ChevronDown className="size-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuItem
              onSelect={() => {
                setPendingNewDraft(true);
                setFileMenuOpen(false);
              }}
              disabled={saveState === "saving" || loading}
            >
              <FilePlus className="size-4" />
              New Draft
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={() => importInputRef.current?.click()}
              disabled={saveState === "saving" || loading}
            >
              <Upload className="size-4" />
              Import YAML…
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={onExportYaml} disabled={loading}>
              <Download className="size-4" />
              Export YAML
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* History */}
        <TooltipProvider delayDuration={300}>
          <div className="flex items-center gap-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="secondary"
                  size="icon"
                  onClick={undo}
                  disabled={!canUndo || saveState === "saving"}
                  aria-label="Undo"
                >
                  <Undo2 className="size-3.5" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                Undo <span className="text-text-muted">Ctrl/Cmd+Z</span>
              </TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="secondary"
                  size="icon"
                  onClick={redo}
                  disabled={!canRedo || saveState === "saving"}
                  aria-label="Redo"
                >
                  <Redo2 className="size-3.5" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                Redo <span className="text-text-muted">Ctrl/Cmd+Shift+Z</span>
              </TooltipContent>
            </Tooltip>
          </div>
        </TooltipProvider>

        {/* YAML commit + Save */}
        <Button
          variant="secondary"
          size="sm"
          onClick={onApplyYaml}
          disabled={loading || saveState === "saving"}
          title="Apply YAML edits to canvas"
        >
          Apply
        </Button>
        {canRebuildCache && onRebuildCache && (
          <Button
            variant="secondary"
            size="sm"
            onClick={onRebuildCache}
            disabled={loading || saveState === "saving" || rebuildingCache}
            title="Rebuild TTS cache for this scenario"
          >
            {rebuildingCache ? "Rebuilding Cache…" : "Rebuild Cache"}
          </Button>
        )}
        <Button size="sm" onClick={onSave} disabled={!canSave}>
          {saveState === "saving" ? "Saving…" : "Save"}
        </Button>

        {/* Help */}
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Keyboard shortcuts">
              <HelpCircle className="size-4" />
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-64">
            <p className="mb-2 text-xs font-semibold text-text-primary">Keyboard shortcuts</p>
            <dl className="space-y-1 text-xs text-text-secondary">
              <div className="flex justify-between">
                <dt>Save</dt>
                <dd className="font-mono text-text-muted">Ctrl/Cmd+S</dd>
              </div>
              <div className="flex justify-between">
                <dt>Undo</dt>
                <dd className="font-mono text-text-muted">Ctrl/Cmd+Z</dd>
              </div>
              <div className="flex justify-between">
                <dt>Redo</dt>
                <dd className="font-mono text-text-muted">Ctrl/Cmd+Shift+Z</dd>
              </div>
              <div className="flex justify-between">
                <dt>Copy block</dt>
                <dd className="font-mono text-text-muted">Ctrl/Cmd+C</dd>
              </div>
              <div className="flex justify-between">
                <dt>Paste block</dt>
                <dd className="font-mono text-text-muted">Ctrl/Cmd+V</dd>
              </div>
            </dl>
            <p className="mt-3 text-[10px] text-text-muted">
              Apply commits YAML editor changes to the canvas.
            </p>
          </PopoverContent>
        </Popover>
      </div>
    </div>
  );
}
