"use client";

import { useCallback } from "react";
import {
  ClipboardCopy,
  ClipboardPaste,
  Ear,
  MessageSquareText,
  PanelRightOpen,
  PhoneOff,
  Split,
  Route,
  TimerReset,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  BRANCH_CASE_COUNT_DEFAULT,
  BRANCH_CASE_COUNT_MIN,
  BRANCH_CASE_COUNT_MAX,
  BUILDER_BLOCK_DND_MIME,
  type BuilderPaletteBlockKind,
} from "@/lib/builder-blocks";
import type { DragEvent as ReactDragEvent } from "react";

const PALETTE_BLOCKS: Array<{
  kind: BuilderPaletteBlockKind;
  title: string;
  description: string;
  icon: typeof MessageSquareText;
}> = [
  {
    kind: "say_something",
    title: "Say / Play",
    description: "Harness speaks a prompt and waits for caller response.",
    icon: MessageSquareText,
  },
  {
    kind: "listen_silence",
    title: "Listen First",
    description: "Silence window so the LLM call-center agent can speak first.",
    icon: Ear,
  },
  {
    kind: "decide_branch",
    title: "Decide + Branch",
    description: "Classifier-driven routing with dynamic branch outputs.",
    icon: Split,
  },
  {
    kind: "time_route",
    title: "Time Route",
    description: "Route by local time windows with explicit default fallback.",
    icon: Route,
  },
  {
    kind: "wait_pause",
    title: "Wait / Pause",
    description: "Clock-only pause without playing audio into the call.",
    icon: TimerReset,
  },
  {
    kind: "hangup_end",
    title: "Hangup / End",
    description: "Terminal block to make flow endings explicit.",
    icon: PhoneOff,
  },
];

interface TurnBlocksPaletteProps {
  open: boolean;
  onToggle: () => void;
  clipboardTurn: { sourceTurnId: string } | null;
  selectedNodeIds: string[];
  hasSelection: boolean;
  onInsertBlock: (kind: BuilderPaletteBlockKind) => void;
  onCopy: () => void;
  onPaste: () => void;
  onDelete: () => void;
}

export function TurnBlocksPalette({
  open,
  onToggle,
  clipboardTurn,
  selectedNodeIds,
  hasSelection,
  onInsertBlock,
  onCopy,
  onPaste,
  onDelete,
}: TurnBlocksPaletteProps) {
  const handlePaletteDragStart = useCallback(
    (event: ReactDragEvent<HTMLButtonElement>, kind: BuilderPaletteBlockKind) => {
      const payload = JSON.stringify({
        kind,
        branchCaseCount:
          kind === "decide_branch" ? BRANCH_CASE_COUNT_DEFAULT : undefined,
      });
      event.dataTransfer.setData(BUILDER_BLOCK_DND_MIME, payload);
      event.dataTransfer.setData("text/plain", kind);
      event.dataTransfer.effectAllowed = "copy";
    },
    []
  );

  return (
    <div className="rounded-xl border border-border bg-bg-elevated shadow-sm">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
      >
        <h2 className="text-sm font-semibold text-text-primary">Turn Blocks</h2>
        <span className="text-xs text-text-muted">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-border px-3 pb-3 pt-2">
          <p className="text-xs text-text-muted">
            Drag blocks onto the canvas, then connect edges.
          </p>
          <div className="space-y-2">
            {PALETTE_BLOCKS.map((block) => (
              <div
                key={block.kind}
                className="rounded-xl border border-border bg-bg-surface px-3 py-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-start gap-2">
                    <div className="mt-0.5 rounded-lg border border-border bg-bg-base p-2 text-text-secondary">
                      <block.icon className="h-3.5 w-3.5" />
                    </div>
                    <div>
                      <p className="text-xs font-medium text-text-primary">{block.title}</p>
                      <p className="mt-1 text-[11px] text-text-muted">{block.description}</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    draggable
                    onDragStart={(event) => handlePaletteDragStart(event, block.kind)}
                    className="rounded-lg border border-border bg-bg-base px-2 py-1 text-[10px] text-text-secondary transition-colors hover:bg-bg-subtle hover:text-text-primary"
                  >
                    Drag
                  </button>
                </div>
                <div className="mt-3 flex items-center justify-between gap-2">
                  <span className="text-[10px] text-text-muted">
                    {block.kind === "decide_branch"
                      ? "Adjust outputs from the node on canvas"
                      : "Quick starter block"}
                  </span>
                  <Button
                    variant="secondary"
                    size="sm"
                    className="h-7 rounded-lg px-2.5 text-[10px]"
                    onClick={() => onInsertBlock(block.kind)}
                  >
                    Add
                  </Button>
                </div>
              </div>
            ))}
          </div>
          <div className="flex items-center justify-between rounded-xl border border-border bg-bg-surface px-2.5 py-2">
            <span className="text-[11px] text-text-muted">
              {selectedNodeIds.length > 0
                ? `Selected: ${selectedNodeIds.join(", ")}`
                : "No block selected"}
            </span>
            <div className="flex gap-1">
              <Button
                variant="secondary"
                size="sm"
                className="h-7 rounded-lg px-2 text-[10px]"
                onClick={onCopy}
                disabled={!hasSelection}
              >
                Copy
              </Button>
              <Button
                variant="secondary"
                size="sm"
                className="h-7 rounded-lg px-2 text-[10px]"
                onClick={onPaste}
                disabled={!clipboardTurn}
              >
                Paste
              </Button>
              <Button
                variant="secondary"
                size="sm"
                className="h-7 rounded-lg border-fail-border px-2 text-[10px] text-fail"
                onClick={onDelete}
                disabled={selectedNodeIds.length === 0}
              >
                Delete
              </Button>
            </div>
          </div>
          <p className="text-[10px] text-text-muted">
            Shortcuts: Ctrl/Cmd+C copy selected block, Ctrl/Cmd+V paste,
            Delete/Backspace remove selected block(s).
            Decision outputs range {BRANCH_CASE_COUNT_MIN}-{BRANCH_CASE_COUNT_MAX}.
          </p>
        </div>
      )}
    </div>
  );
}

interface CollapsedTurnBlocksRailProps {
  clipboardTurn: { sourceTurnId: string } | null;
  hasSelection: boolean;
  selectedNodeCount: number;
  onExpand: () => void;
  onInsertBlock: (kind: BuilderPaletteBlockKind) => void;
  onCopy: () => void;
  onPaste: () => void;
  onDelete: () => void;
}

export function CollapsedTurnBlocksRail({
  clipboardTurn,
  hasSelection,
  selectedNodeCount,
  onExpand,
  onInsertBlock,
  onCopy,
  onPaste,
  onDelete,
}: CollapsedTurnBlocksRailProps) {
  return (
    <div className="hidden flex-col items-center gap-2 rounded-xl border border-border bg-bg-surface px-1.5 py-2 shadow-sm lg:flex">
      <button
        type="button"
        onClick={onExpand}
        title="Expand builder panel"
        aria-label="Expand builder panel"
        className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-bg-base text-text-secondary transition-colors hover:bg-bg-subtle hover:text-text-primary"
      >
        <PanelRightOpen className="h-4 w-4" />
      </button>
      <div className="h-px w-6 bg-border" />
      {PALETTE_BLOCKS.map((block) => (
        <button
          key={block.kind}
          type="button"
          onClick={() => onInsertBlock(block.kind)}
          title={block.title}
          aria-label={block.title}
          className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-border bg-bg-base text-text-secondary transition-colors hover:bg-bg-subtle hover:text-text-primary"
        >
          <block.icon className="h-4 w-4" />
        </button>
      ))}
      <div className="h-px w-6 bg-border" />
      <button
        type="button"
        onClick={onCopy}
        title={hasSelection ? `Copy ${selectedNodeCount} selected block(s)` : "Copy selected block"}
        aria-label="Copy selected block"
        disabled={!hasSelection}
        className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-bg-base text-text-secondary transition-colors hover:bg-bg-subtle hover:text-text-primary disabled:opacity-40"
      >
        <ClipboardCopy className="h-3.5 w-3.5" />
      </button>
      <button
        type="button"
        onClick={onPaste}
        title={clipboardTurn ? "Paste copied block" : "Paste copied block"}
        aria-label="Paste copied block"
        disabled={!clipboardTurn}
        className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-bg-base text-text-secondary transition-colors hover:bg-bg-subtle hover:text-text-primary disabled:opacity-40"
      >
        <ClipboardPaste className="h-3.5 w-3.5" />
      </button>
      <button
        type="button"
        onClick={onDelete}
        title={hasSelection ? `Delete ${selectedNodeCount} selected block(s)` : "Delete selected block"}
        aria-label="Delete selected block"
        disabled={!hasSelection}
        className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-fail-border bg-fail-bg/40 text-fail transition-colors hover:bg-fail-bg disabled:opacity-40"
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
      <span className="[writing-mode:vertical-rl] pt-1 text-[10px] uppercase tracking-[0.24em] text-text-muted">
        Blocks
      </span>
    </div>
  );
}
