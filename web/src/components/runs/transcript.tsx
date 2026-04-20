import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { DECISION_DEFAULT_SLOT } from "@/lib/decision-slots";
import { findActiveTranscriptTurn } from "@/lib/transcript-playback";
import type {
  ConversationTurn,
  RunEvent,
  ScenarioDefinition,
  ScenarioTurn,
} from "@/lib/api";

interface TranscriptProps {
  turns: ConversationTurn[];
  events?: RunEvent[];
  scenario?: ScenarioDefinition | null;
  currentTimeMs?: number;
}

type BranchArm = {
  selector: string;
  target: string;
};

type BranchDecision = {
  turnId: string;
  turnNumber: number;
  visit?: number;
  conditionMatched: string;
  botSnippet?: string;
  nextTurnId?: string;
  notTakenArms: BranchArm[];
};

function _asPositiveInt(value: unknown): number | null {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  const integer = Math.trunc(parsed);
  return integer > 0 ? integer : null;
}

function _normalizeCondition(value: string): string {
  return value.trim().toLowerCase();
}

function _findScenarioTurn(
  scenario: ScenarioDefinition | null | undefined,
  turnId: string
): ScenarioTurn | null {
  if (!scenario) {
    return null;
  }
  const found = scenario.turns.find((turn) => turn.id === turnId);
  return found ?? null;
}

function _buildBranchDecisionIndex(
  events: RunEvent[],
  scenario: ScenarioDefinition | null | undefined
): Map<number, BranchDecision> {
  const decisions = new Map<number, BranchDecision>();

  for (const event of events) {
    if (event.type !== "branch_decision") {
      continue;
    }
    const detail = event.detail;
    if (!detail || typeof detail !== "object") {
      continue;
    }

    const turnNumber = _asPositiveInt(detail.turn_number);
    const turnId =
      typeof detail.turn_id === "string" ? detail.turn_id.trim() : "";
    const conditionMatched =
      typeof detail.condition_matched === "string"
        ? detail.condition_matched.trim()
        : "";

    if (!turnNumber || !turnId || !conditionMatched) {
      continue;
    }

    const turn = _findScenarioTurn(scenario, turnId);
    const notTakenArms: BranchArm[] = [];
    let nextTurnId: string | undefined;

    if (turn?.branching) {
      const normalized = _normalizeCondition(conditionMatched);
      const matchedCase =
        turn.branching.cases.find(
          (candidate) => _normalizeCondition(candidate.condition) === normalized
        ) ?? null;

      const takenSelector = matchedCase?.condition ?? DECISION_DEFAULT_SLOT;
      nextTurnId = matchedCase?.next ?? turn.branching.default;

      for (const candidate of turn.branching.cases) {
        const isTaken =
          _normalizeCondition(candidate.condition) ===
          _normalizeCondition(takenSelector);
        if (!isTaken) {
          notTakenArms.push({
            selector: candidate.condition,
            target: candidate.next,
          });
        }
      }

      if (takenSelector !== DECISION_DEFAULT_SLOT) {
        notTakenArms.push({
          selector: DECISION_DEFAULT_SLOT,
          target: turn.branching.default,
        });
      }
    }

    decisions.set(turnNumber, {
      turnId,
      turnNumber,
      visit: _asPositiveInt(detail.visit) ?? undefined,
      conditionMatched,
      botSnippet:
        typeof detail.bot_response_snippet_redacted === "string"
          ? detail.bot_response_snippet_redacted
          : undefined,
      nextTurnId,
      notTakenArms,
    });
  }

  return decisions;
}

export function Transcript({
  turns,
  events = [],
  scenario = null,
  currentTimeMs,
}: TranscriptProps) {
  const activeTurnElRef = useRef<HTMLDivElement | null>(null);
  const prevActiveKeyRef = useRef<string | null>(null);

  const activeTurn = findActiveTranscriptTurn(turns, currentTimeMs);

  const activeTurnKey = activeTurn
    ? `${activeTurn.turn_id ?? "turn"}:${activeTurn.speaker}:${activeTurn.turn_number ?? "n"}:${turns.indexOf(activeTurn)}`
    : null;

  // Scroll the active turn into view when it changes
  useEffect(() => {
    if (activeTurnKey && activeTurnKey !== prevActiveKeyRef.current) {
      prevActiveKeyRef.current = activeTurnKey;
      activeTurnElRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    }
  }, [activeTurnKey]);

  if (!turns.length) {
    return (
      <p className="text-sm text-text-muted py-4">No conversation recorded.</p>
    );
  }

  const branchDecisions = _buildBranchDecisionIndex(events, scenario);

  return (
    <div className="space-y-3">
      {turns.map((turn, i) => {
        const isHarness = turn.speaker === "harness";
        const turnNumber = turn.turn_number ?? i + 1;
        const branchDecision = branchDecisions.get(turnNumber);
        const rowKey = `${turn.turn_id ?? "turn"}:${turn.speaker}:${turn.turn_number ?? "n"}:${i}`;
        const isActive = rowKey === activeTurnKey;
        return (
          <div
            key={rowKey}
            ref={isActive ? (el) => { activeTurnElRef.current = el; } : undefined}
            className={cn(
              "flex flex-col max-w-[75%]",
              isHarness ? "items-start" : "items-end ml-auto"
            )}
          >
            <div className="flex items-center gap-2 mb-1">
              {turn.turn_id && (
                <span className="font-mono text-[10px] text-text-muted bg-bg-elevated border border-border px-1.5 py-0.5 rounded">
                  {turn.turn_id}
                </span>
              )}
              <span className="text-[10px] text-text-muted uppercase tracking-wide">
                {turn.speaker}
              </span>
              {isActive ? (
                <span
                  className={cn(
                    "inline-flex items-center rounded-full px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-wide",
                    isHarness
                      ? "bg-info-bg text-info border border-info-border"
                      : "bg-brand-muted text-brand border border-brand/40",
                  )}
                >
                  Playing
                </span>
              ) : null}
            </div>
            <div
              className={cn(
                "rounded-lg px-4 py-2.5 font-mono text-xs leading-relaxed transition-[box-shadow,border-color,background-color,color]",
                isHarness
                  ? "bg-brand-muted border border-info-border text-info"
                  : "bg-bg-elevated border border-border text-text-secondary",
                isActive &&
                  isHarness &&
                  "ring-2 ring-info ring-offset-1 ring-offset-bg-base shadow-[0_0_0_1px_rgba(14,165,233,0.18)]",
                isActive &&
                  !isHarness &&
                  "border-brand/60 bg-bg-subtle text-text-primary ring-2 ring-brand/60 ring-offset-1 ring-offset-bg-base shadow-lg"
              )}
            >
              {turn.text}
            </div>
            {branchDecision && (
              <div className="mt-2 w-full rounded-md border border-border bg-bg-elevated px-3 py-2">
                <p className="font-mono text-[11px] text-info">
                  branch -&gt; {branchDecision.nextTurnId ?? DECISION_DEFAULT_SLOT} (matched: &quot;
                  {branchDecision.conditionMatched}&quot;)
                </p>
                {branchDecision.visit && (
                  <p className="mt-1 text-[11px] text-text-muted font-mono">
                    turn_id={branchDecision.turnId} visit={branchDecision.visit} turn_number=
                    {branchDecision.turnNumber}
                  </p>
                )}
                {branchDecision.botSnippet && (
                  <p className="mt-1 text-[11px] italic text-text-muted">
                    &quot;{branchDecision.botSnippet}&quot;
                  </p>
                )}
                {branchDecision.notTakenArms.length > 0 && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-[11px] text-text-muted">
                      Not taken ({branchDecision.notTakenArms.length})
                    </summary>
                    <div className="mt-1 space-y-1">
                      {branchDecision.notTakenArms.map((arm) => (
                        <p
                          key={`${branchDecision.turnNumber}:${arm.selector}:${arm.target}`}
                          className="text-[11px] font-mono text-text-muted"
                        >
                          {arm.selector} -&gt; {arm.target}
                        </p>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
