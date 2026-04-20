import useSWR from "swr";
import { apiFetch, authHeaders, buildApiUrl, fetcher } from "./fetcher";
import type {
  PackRunCancelResponse,
  PackRunChildrenResponse,
  PackRunDetail,
  PackRunMarkFailedResponse,
  PackRunSummary,
  PackRunStartResponse,
  ScenarioPackDetail,
  ScenarioPackSummary,
  ScenarioPackUpsertRequest,
} from "./types";

interface RunPackDispatchOptions {
  idempotencyKey?: string;
  transportProfileId?: string;
  dialTarget?: string;
}

export function buildRunPackDispatchRequest(
  headers: HeadersInit,
  opts?: RunPackDispatchOptions
): { headers: Headers; body?: string } {
  const requestHeaders = new Headers(headers);
  const idempotencyKey = opts?.idempotencyKey?.trim();
  if (idempotencyKey) {
    requestHeaders.set("Idempotency-Key", idempotencyKey);
  }
  const transportProfileId = opts?.transportProfileId?.trim();
  const dialTarget = opts?.dialTarget?.trim();
  if (transportProfileId || dialTarget) {
    requestHeaders.set("Content-Type", "application/json");
    const body: Record<string, string> = {};
    if (transportProfileId) {
      body.transport_profile_id = transportProfileId;
    }
    if (dialTarget) {
      body.dial_target = dialTarget;
    }
    return {
      headers: requestHeaders,
      body: JSON.stringify(body),
    };
  }
  return { headers: requestHeaders };
}

export function usePacks() {
  return useSWR<ScenarioPackSummary[]>("/packs/", fetcher);
}

export function usePack(packId: string | null) {
  return useSWR<ScenarioPackDetail>(packId ? `/packs/${packId}` : null, fetcher);
}

export function usePackRuns(params?: { packId?: string; state?: string }) {
  const key = buildApiUrl("/pack-runs/", {
    pack_id: params?.packId,
    state: params?.state,
  });
  return useSWR<PackRunSummary[]>(key, fetcher, {
    refreshInterval: 5000,
  });
}

export function usePackRun(packRunId: string | null) {
  return useSWR<PackRunDetail>(packRunId ? `/pack-runs/${packRunId}` : null, fetcher, {
    refreshInterval: (data) =>
      data?.state === "pending" || data?.state === "running" ? 3000 : 0,
  });
}

export function usePackRunChildren(
  packRunId: string | null,
  params?: {
    state?: string;
    gateResult?: string;
    failuresOnly?: boolean;
    sortBy?: "failures_first" | "order" | "state" | "gate_result" | "scenario_id";
    sortDir?: "asc" | "desc";
    limit?: number;
    offset?: number;
  }
) {
  let key: string | null = null;
  if (packRunId) {
    key = buildApiUrl(`/pack-runs/${packRunId}/runs`, {
      state: params?.state,
      gate_result: params?.gateResult,
      failures_only: params?.failuresOnly ? "true" : undefined,
      sort_by: params?.sortBy,
      sort_dir: params?.sortDir,
      limit: params?.limit,
      offset: params?.offset,
    });
  }
  return useSWR<PackRunChildrenResponse>(key, fetcher, {
    refreshInterval: key ? 3000 : 0,
  });
}

export async function runPack(
  packId: string,
  opts?: RunPackDispatchOptions
): Promise<PackRunStartResponse> {
  const headers = await authHeaders();
  const request = buildRunPackDispatchRequest(headers, opts);
  return apiFetch<PackRunStartResponse>(`/packs/${packId}/run`, {
    method: "POST",
    headers: request.headers,
    body: request.body,
    context: "Run pack failed",
  });
}

export async function createPack(
  payload: ScenarioPackUpsertRequest
): Promise<ScenarioPackDetail> {
  return apiFetch<ScenarioPackDetail>("/packs/", {
    method: "POST",
    json: payload,
    context: "Create pack failed",
  });
}

export async function updatePack(
  packId: string,
  payload: ScenarioPackUpsertRequest
): Promise<ScenarioPackDetail> {
  return apiFetch<ScenarioPackDetail>(`/packs/${packId}`, {
    method: "PUT",
    json: payload,
    context: "Update pack failed",
  });
}

export async function deletePack(packId: string): Promise<void> {
  await apiFetch<void>(`/packs/${packId}`, {
    method: "DELETE",
    context: "Delete pack failed",
  });
}

export async function cancelPackRun(packRunId: string): Promise<PackRunCancelResponse> {
  return apiFetch<PackRunCancelResponse>(`/pack-runs/${packRunId}/cancel`, {
    method: "POST",
    context: "Cancel pack run failed",
  });
}

export async function markPackRunFailed(
  packRunId: string,
  reason?: string
): Promise<PackRunMarkFailedResponse> {
  const payload = reason?.trim() ? { reason: reason.trim() } : {};
  return apiFetch<PackRunMarkFailedResponse>(`/pack-runs/${packRunId}/mark-failed`, {
    method: "POST",
    json: payload,
    context: "Mark pack run failed",
  });
}
