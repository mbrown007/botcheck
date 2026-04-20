import useSWR from "swr";

import { apiFetch, buildApiUrl, fetcher } from "./fetcher";
import type {
  GraiEvalArtifactResponse,
  GraiEvalMatrixResponse,
  GraiEvalReportResponse,
  GraiEvalResultFilters,
  GraiEvalResultPageResponse,
  GraiEvalRunCancelResponse,
  GraiEvalRunCreateRequest,
  GraiEvalRunHistorySummary,
  GraiEvalRunProgressResponse,
  GraiEvalRunResponse,
  GraiEvalSuiteDetail,
  GraiEvalSuiteImportRequest,
  GraiEvalSuiteSummary,
  GraiEvalSuiteUpsertRequest,
} from "./types";

export function useGraiEvalSuites() {
  return useSWR<GraiEvalSuiteSummary[]>("/grai/suites", fetcher);
}

export function useGraiEvalSuite(suiteId: string | null) {
  return useSWR<GraiEvalSuiteDetail>(suiteId ? `/grai/suites/${suiteId}` : null, fetcher);
}

export function useGraiEvalRun(runId: string | null) {
  return useSWR<GraiEvalRunResponse>(runId ? `/grai/runs/${runId}` : null, fetcher);
}

export function useGraiEvalRunProgress(runId: string | null, enabled = true) {
  return useSWR<GraiEvalRunProgressResponse>(
    enabled && runId ? `/grai/runs/${runId}/progress` : null,
    fetcher,
    {
      refreshInterval: (data) =>
        data?.status === "pending" || data?.status === "running" ? 2000 : 0,
    }
  );
}

export function useGraiEvalRunReport(
  runId: string | null,
  filters: GraiEvalResultFilters,
  enabled = true
) {
  const path =
    enabled && runId
      ? buildApiUrl(`/grai/runs/${runId}/report`, {
          prompt_id: filters.prompt_id,
          assertion_type: filters.assertion_type,
          tag: filters.tag,
          status: filters.status,
          destination_index: filters.destination_index,
        })
      : null;
  return useSWR<GraiEvalReportResponse>(path, fetcher);
}

export function useGraiEvalRunResults(
  runId: string | null,
  filters: GraiEvalResultFilters & { cursor?: string | null; limit?: number },
  enabled = true
) {
  const path =
    enabled && runId
      ? buildApiUrl(`/grai/runs/${runId}/results`, {
          prompt_id: filters.prompt_id,
          assertion_type: filters.assertion_type,
          tag: filters.tag,
          status: filters.status,
          destination_index: filters.destination_index,
          cursor: filters.cursor,
          limit: filters.limit ?? 20,
        })
      : null;
  return useSWR<GraiEvalResultPageResponse>(path, fetcher);
}

export function useGraiEvalSuiteRuns(suiteId: string | null, limit = 20) {
  return useSWR<GraiEvalRunHistorySummary[]>(
    suiteId ? buildApiUrl(`/grai/suites/${suiteId}/runs`, { limit }) : null,
    fetcher
  );
}

export function useGraiEvalRunHistoryIndex(limitPerSuite = 100) {
  const suitesResponse = useGraiEvalSuites();
  const suiteIds = (suitesResponse.data ?? [])
    .map((suite) => suite.suite_id)
    .sort();
  const indexKey =
    suitesResponse.data !== undefined
      ? ["/grai/suites/runs/index", limitPerSuite, suiteIds.join(",")]
      : null;
  const historyResponse = useSWR<GraiEvalRunHistorySummary[]>(
    indexKey,
    async ([, limit, joinedSuiteIds]: readonly [string, number, string]) => {
      if (!joinedSuiteIds) {
        return [];
      }
      const responses = await Promise.all(
        joinedSuiteIds.split(",").map((suiteId) =>
          apiFetch<GraiEvalRunHistorySummary[]>(
            buildApiUrl(`/grai/suites/${encodeURIComponent(suiteId)}/runs`, { limit }),
            { context: "Load grai eval history index failed" }
          )
        )
      );
      return responses
        .flat()
        .sort((left, right) => (right.created_at ?? "").localeCompare(left.created_at ?? ""));
    },
    {
      refreshInterval: 30_000,
    }
  );

  return {
    ...historyResponse,
    error: suitesResponse.error ?? historyResponse.error,
  };
}

export function useGraiEvalRunMatrix(runId: string | null, enabled = true) {
  return useSWR<GraiEvalMatrixResponse>(
    enabled && runId ? `/grai/runs/${runId}/matrix` : null,
    fetcher,
    {
      refreshInterval: (data) =>
        data?.status === "pending" || data?.status === "running" ? 2000 : 0,
    }
  );
}

export async function updateGraiEvalSuite(
  suiteId: string,
  body: GraiEvalSuiteUpsertRequest
): Promise<GraiEvalSuiteDetail> {
  return apiFetch<GraiEvalSuiteDetail>(`/grai/suites/${suiteId}`, {
    method: "PUT",
    json: body,
    context: "Update grai eval suite failed",
  });
}

export async function deleteGraiEvalSuite(suiteId: string): Promise<void> {
  await apiFetch<void>(`/grai/suites/${suiteId}`, {
    method: "DELETE",
    context: "Delete grai eval suite failed",
  });
}

export async function createGraiEvalSuite(
  body: GraiEvalSuiteUpsertRequest
): Promise<GraiEvalSuiteDetail> {
  return apiFetch<GraiEvalSuiteDetail>("/grai/suites", {
    method: "POST",
    json: body,
    context: "Create grai eval suite failed",
  });
}

export async function importGraiEvalSuite(
  body: GraiEvalSuiteImportRequest
): Promise<GraiEvalSuiteDetail> {
  return apiFetch<GraiEvalSuiteDetail>("/grai/suites/import", {
    method: "POST",
    json: body,
    context: "Import grai eval suite failed",
  });
}

export async function createGraiEvalRun(
  body: GraiEvalRunCreateRequest
): Promise<GraiEvalRunResponse> {
  return apiFetch<GraiEvalRunResponse>("/grai/runs", {
    method: "POST",
    json: body,
    context: "Create grai eval run failed",
  });
}

export async function cancelGraiEvalRun(evalRunId: string): Promise<GraiEvalRunCancelResponse> {
  return apiFetch<GraiEvalRunCancelResponse>(`/grai/runs/${evalRunId}/cancel`, {
    method: "POST",
    context: "Cancel grai eval run failed",
  });
}

export async function getGraiEvalArtifact(
  evalRunId: string,
  evalResultId: string
): Promise<GraiEvalArtifactResponse> {
  return apiFetch<GraiEvalArtifactResponse>(
    `/grai/runs/${evalRunId}/results/${evalResultId}/artifact`,
    { context: "Load grai eval artifact failed" }
  );
}
