"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Card, CardBody } from "@/components/ui/card";
import { ScoreBar } from "@/components/ui/score-bar";
import { StatusBadge } from "@/components/ui/badge";
import type { RunScore } from "@/lib/api";
import { formatScoreReasoning } from "@/lib/score-reasoning";

const DIMENSIONS = [
  { key: "routing", label: "Call Routing" },
  { key: "policy", label: "Policy Adherence" },
  { key: "jailbreak", label: "Jailbreak Resistance" },
  { key: "disclosure", label: "Disclosure" },
  { key: "pii_handling", label: "PII Handling" },
  { key: "reliability", label: "Reliability" },
  { key: "role_integrity", label: "Role Integrity" },
];

const MAX_CHARS = 140;

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"] as const;
type Severity = (typeof SEVERITY_ORDER)[number];

function pickEvidenceQuote(score: RunScore | undefined, passed: boolean): string {
  const findings = score?.findings;
  if (!findings?.length) return "";

  // When failing, prefer the most severe negative finding.
  // When passing, prefer the most severe positive finding.
  // Fall back to any finding with a quoted_text if no preferred polarity exists.
  const wantPositive = passed;

  const preferred = findings
    .filter((f) => typeof f?.quoted_text === "string" && f.positive === wantPositive)
    .sort(
      (a, b) =>
        SEVERITY_ORDER.indexOf(a.severity as Severity) -
        SEVERITY_ORDER.indexOf(b.severity as Severity)
    );

  if (preferred.length > 0) return preferred[0].quoted_text;

  return findings.find((f) => typeof f?.quoted_text === "string")?.quoted_text ?? "";
}

function labelForDimension(key: string): string {
  const found = DIMENSIONS.find((item) => item.key === key);
  if (found) {
    return found.label;
  }
  return key
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function resolveVisibleDimensions(
  scores: Record<string, RunScore>,
  failedDimensions: string[],
  dimensionKeys: string[]
): string[] {
  const selected = new Set<string>();
  for (const key of dimensionKeys) {
    if (key) {
      selected.add(key);
    }
  }
  for (const key of Object.keys(scores)) {
    selected.add(key);
  }
  for (const key of failedDimensions) {
    selected.add(key);
  }

  if (selected.size === 0) {
    return DIMENSIONS.map(({ key }) => key);
  }

  const knownOrder = DIMENSIONS.map(({ key }) => key);
  const known = knownOrder.filter((key) => selected.has(key));
  const unknown = Array.from(selected).filter((key) => !knownOrder.includes(key)).sort();
  return [...known, ...unknown];
}

interface ScoreCardProps {
  label: string;
  score: RunScore | undefined;
  failed: boolean;
}

function ScoreCard({ label, score, failed }: ScoreCardProps) {
  const [expanded, setExpanded] = useState(false);

  const pct = score?.score != null ? Math.round(score.score * 100) : null;
  const isFlagMetric = score?.metric_type === "flag";
  const passed = score?.passed ?? (score?.score ?? 0) >= 0.5;
  const reasoning = score?.reasoning ?? "";
  const formattedReasoning = formatScoreReasoning(reasoning);
  const evidence = pickEvidenceQuote(score, passed);

  const reasoningText = [formattedReasoning.summary, ...formattedReasoning.details]
    .filter(Boolean)
    .join(" ");
  const reasoningTruncated = reasoningText.length > MAX_CHARS;
  const evidenceTruncated = evidence.length > MAX_CHARS;
  const canExpand = reasoningTruncated || evidenceTruncated;

  const displayReasoning =
    expanded || !reasoningTruncated
      ? formattedReasoning
      : formatScoreReasoning(`${reasoningText.slice(0, MAX_CHARS - 3)}...`);
  const displayEvidence = expanded || !evidenceTruncated ? evidence : `${evidence.slice(0, MAX_CHARS - 3)}...`;

  return (
    <Card className={failed ? "border-fail-border" : undefined}>
      <CardBody className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-text-secondary">{label}</span>
          {failed && <StatusBadge value="fail" label="FAIL" />}
        </div>

        {isFlagMetric ? (
          score && (score.passed != null || score.score != null) ? (
            <StatusBadge
              value={passed ? "pass" : "fail"}
              label={passed ? "PASS" : "FAIL"}
            />
          ) : (
            <p className="text-xs text-text-muted">Not scored</p>
          )
        ) : pct != null ? (
          <ScoreBar label="" value={pct} />
        ) : (
          <p className="text-xs text-text-muted">Not scored</p>
        )}

        {reasoning && (
          <div className="space-y-1 text-xs leading-relaxed text-text-secondary">
            {displayReasoning.summary ? <p>{displayReasoning.summary}</p> : null}
            {displayReasoning.details.length > 0 ? (
              <ul className="list-disc space-y-1 pl-4 text-text-muted">
                {displayReasoning.details.map((detail) => (
                  <li key={detail}>{detail}</li>
                ))}
              </ul>
            ) : null}
          </div>
        )}
        {evidence && (
          <p className="text-xs italic text-text-muted">&quot;{displayEvidence}&quot;</p>
        )}

        {canExpand && (
          <button
            onClick={() => setExpanded((prev) => !prev)}
            className="flex items-center gap-1 text-xs text-text-muted hover:text-text-secondary transition-colors"
          >
            {expanded ? (
              <>
                <ChevronDown className="h-3 w-3" />
                <span>Show less</span>
              </>
            ) : (
              <>
                <ChevronRight className="h-3 w-3" />
                <span>Show more</span>
              </>
            )}
          </button>
        )}
      </CardBody>
    </Card>
  );
}

interface ScoreCardsProps {
  scores?: Record<string, RunScore>;
  failedDimensions?: string[];
  dimensionKeys?: string[];
}

export function ScoreCards({
  scores = {},
  failedDimensions = [],
  dimensionKeys = [],
}: ScoreCardsProps) {
  const visibleDimensions = resolveVisibleDimensions(scores, failedDimensions, dimensionKeys);
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
      {visibleDimensions.map((key) => (
        <ScoreCard
          key={key}
          label={labelForDimension(key)}
          score={scores[key]}
          failed={failedDimensions.includes(key)}
        />
      ))}
    </div>
  );
}
