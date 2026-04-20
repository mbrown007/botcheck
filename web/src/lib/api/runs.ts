import useSWR from "swr";
import { apiFetch, apiFetchBlob, buildApiUrl, fetcher } from "./fetcher";
import type {
  RunResponse,
  GateResponse,
  TenantInfo,
  FeaturesResponse,
  RunOperatorActionResponse,
} from "./types";

export function useRuns(limit = 100, offset = 0) {
  return useSWR<RunResponse[]>(buildApiUrl("/runs/", { limit, offset }), fetcher, {
    refreshInterval: 5000,
  });
}

export function useRun(id: string | null) {
  return useSWR<RunResponse>(id ? `/runs/${id}` : null, fetcher, {
    refreshInterval: (data) =>
      data?.state === "pending" || data?.state === "judging" || data?.state === "running"
        ? 3000
        : 0,
  });
}

export function useScheduleRuns(scheduleId: string | null) {
  return useSWR<RunResponse[]>(
    scheduleId ? `/schedules/${scheduleId}/runs` : null,
    fetcher,
    { refreshInterval: 15000 },
  );
}

export function useGate(id: string | null) {
  return useSWR<GateResponse>(id ? `/runs/${id}/gate` : null, fetcher);
}

export function useTenant() {
  return useSWR<TenantInfo>("/tenants/me", fetcher);
}

export function useFeatures() {
  return useSWR<FeaturesResponse>("/features", fetcher, {
    refreshInterval: 60000,
  });
}

export function buildCreateRunPayload(
  scenarioId?: string | null,
  dialTarget?: string,
  transportProfileId?: string,
  aiScenarioId?: string,
  trunkPoolId?: string
): {
  scenario_id?: string;
  ai_scenario_id?: string;
  dial_target?: string;
  transport_profile_id?: string;
  trunk_pool_id?: string;
} {
  const payload: {
    scenario_id?: string;
    ai_scenario_id?: string;
    dial_target?: string;
    transport_profile_id?: string;
    trunk_pool_id?: string;
  } = {};
  const trimmedScenarioId = scenarioId?.trim();
  const trimmedAiScenarioId = aiScenarioId?.trim();
  const trimmedDialTarget = dialTarget?.trim();
  const trimmedTransportProfileId = transportProfileId?.trim();
  const trimmedTrunkPoolId = trunkPoolId?.trim();
  if (trimmedScenarioId) {
    payload.scenario_id = trimmedScenarioId;
  }
  if (trimmedAiScenarioId) {
    payload.ai_scenario_id = trimmedAiScenarioId;
  }
  if (trimmedDialTarget) {
    payload.dial_target = trimmedDialTarget;
  }
  if (trimmedTransportProfileId) {
    payload.transport_profile_id = trimmedTransportProfileId;
  }
  if (trimmedTrunkPoolId) {
    payload.trunk_pool_id = trimmedTrunkPoolId;
  }
  return payload;
}

export async function createRun(
  scenarioId?: string | null,
  dialTarget?: string,
  transportProfileId?: string,
  aiScenarioId?: string,
  trunkPoolId?: string
): Promise<RunResponse> {
  const payload = buildCreateRunPayload(
    scenarioId,
    dialTarget,
    transportProfileId,
    aiScenarioId,
    trunkPoolId
  );
  return apiFetch<RunResponse>("/runs/", {
    method: "POST",
    json: payload,
    context: "Create run failed",
  });
}

export async function getRunRecordingBlob(runId: string): Promise<Blob> {
  return apiFetchBlob(`/runs/${runId}/recording`, {
    context: "Load recording failed",
  });
}

export async function stopRun(
  runId: string,
  reason?: string
): Promise<RunOperatorActionResponse> {
  const payload = reason?.trim() ? { reason: reason.trim() } : {};
  return apiFetch<RunOperatorActionResponse>(`/runs/${runId}/stop`, {
    method: "POST",
    json: payload,
    context: "Stop run failed",
  });
}

export async function markRunFailed(
  runId: string,
  reason?: string
): Promise<RunOperatorActionResponse> {
  const payload = reason?.trim() ? { reason: reason.trim() } : {};
  return apiFetch<RunOperatorActionResponse>(`/runs/${runId}/mark-failed`, {
    method: "POST",
    json: payload,
    context: "Mark run failed failed",
  });
}
