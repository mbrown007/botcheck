interface FormattedScoreReasoning {
  summary: string;
  details: string[];
}

function humanizeMetric(metric: string): string {
  switch (metric) {
    case "p95_gap_ms":
    case "p95_response_gap_ms":
      return "P95 response gap";
    case "interruptions":
      return "Interruptions";
    case "long_pauses":
      return "Long pauses";
    case "interruption_recovery_pct":
      return "Interruption recovery";
    case "turn_taking_efficiency_pct":
      return "Turn-taking efficiency";
    default:
      return metric.replaceAll("_", " ");
  }
}

function formatMetricValue(key: string, value: string): string {
  if (key.endsWith("_pct")) {
    return `${value}%`;
  }
  if (key.endsWith("_ms")) {
    return `${value} ms`;
  }
  return value;
}

function formatTimingPart(part: string): string {
  const inner = part.slice("timing(".length, -1);
  const segments = inner
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const bits = segments.map((segment) => {
    const [rawKey, rawValue] = segment.split("=", 2);
    const key = rawKey?.trim() ?? "";
    const value = rawValue?.trim() ?? "";
    if (!key || !value) {
      return segment;
    }
    return `${humanizeMetric(key)}: ${formatMetricValue(key, value)}`;
  });
  return `Timing: ${bits.join(", ")}`;
}

function formatThresholdComparison(segment: string): string {
  const match = segment.match(/^([a-z0-9_]+)=([0-9.]+)\s*([<>])\s*([0-9.]+)$/i);
  if (!match) {
    return segment;
  }
  const [, metric, actual, comparator, threshold] = match;
  const label = humanizeMetric(metric);
  const formattedActual = formatMetricValue(metric, actual);
  const formattedThreshold = formatMetricValue(metric, threshold);
  return `${label}: ${formattedActual} ${comparator} ${formattedThreshold}`;
}

export function formatScoreReasoning(reasoning: string): FormattedScoreReasoning {
  const trimmed = reasoning.trim();
  if (!trimmed) {
    return { summary: "", details: [] };
  }

  const parts = trimmed
    .split("|")
    .map((part) => part.trim())
    .filter(Boolean);

  if (parts.length === 0) {
    return { summary: "", details: [] };
  }

  const [summary, ...rest] = parts;
  const details: string[] = [];

  for (const part of rest) {
    if (part.startsWith("timing(") && part.endsWith(")")) {
      details.push(formatTimingPart(part));
      continue;
    }
    if (part === "timing_within_thresholds") {
      details.push("Timing was within configured thresholds.");
      continue;
    }
    if (part.startsWith("failures=") || part.startsWith("warnings=")) {
      const separatorIndex = part.indexOf("=");
      const rawLabel = separatorIndex >= 0 ? part.slice(0, separatorIndex) : part;
      const rawBody = separatorIndex >= 0 ? part.slice(separatorIndex + 1) : "";
      const label = rawLabel === "failures" ? "Failures" : "Warnings";
      const items = rawBody
        .split(";")
        .map((item) => item.trim())
        .filter(Boolean)
        .map(formatThresholdComparison);
      details.push(`${label}: ${items.join("; ")}`);
      continue;
    }
    details.push(part);
  }

  return { summary, details };
}
