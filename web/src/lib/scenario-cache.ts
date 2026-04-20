import type { ScenarioCacheStateResponse, ScenarioCacheTurnState } from "@/lib/api/types";

interface ScenarioCacheTurnLookupEntry {
  status: ScenarioCacheTurnState["status"];
  key: string | null;
}

export function buildScenarioCacheTurnLookup(
  cacheState: ScenarioCacheStateResponse | null | undefined
): Record<string, ScenarioCacheTurnLookupEntry> {
  const entries = cacheState?.turn_states ?? [];
  return Object.fromEntries(
    entries.map((row) => [row.turn_id, { status: row.status, key: row.key ?? null }])
  );
}

export function scenarioCacheObjectPath(
  bucketName: string | null | undefined,
  key: string | null | undefined
): string | null {
  const normalizedKey = key?.trim();
  if (!normalizedKey) {
    return null;
  }
  const normalizedBucket = bucketName?.trim();
  if (!normalizedBucket) {
    return normalizedKey;
  }
  return `s3://${normalizedBucket}/${normalizedKey}`;
}

export function scenarioCacheCoverageLabel(
  cacheState: ScenarioCacheStateResponse | null | undefined
): string | null {
  if (!cacheState) {
    return null;
  }
  return `${cacheState.cached_turns + cacheState.skipped_turns}/${cacheState.total_harness_turns}`;
}
