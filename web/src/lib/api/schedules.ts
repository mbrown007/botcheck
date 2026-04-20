import useSWR from "swr";
import { apiFetch, fetcher } from "./fetcher";
import type {
  ScheduleResponse,
  ScheduleCreateRequest,
  SchedulePatchRequest,
  SchedulePreviewResponse,
} from "./types";

export function useSchedules() {
  return useSWR<ScheduleResponse[]>("/schedules/", fetcher, {
    refreshInterval: 10000,
  });
}

export async function createSchedule(
  payload: ScheduleCreateRequest
): Promise<ScheduleResponse> {
  return apiFetch<ScheduleResponse>("/schedules/", {
    method: "POST",
    json: payload,
    context: "Create schedule failed",
  });
}

export async function previewSchedule(
  cronExpr: string,
  timezone?: string,
  count = 5
): Promise<SchedulePreviewResponse> {
  return apiFetch<SchedulePreviewResponse>("/schedules/preview", {
    method: "POST",
    json: {
      cron_expr: cronExpr,
      timezone,
      count,
    },
    context: "Schedule preview failed",
  });
}

export async function patchSchedule(
  scheduleId: string,
  payload: SchedulePatchRequest
): Promise<ScheduleResponse> {
  return apiFetch<ScheduleResponse>(`/schedules/${scheduleId}`, {
    method: "PATCH",
    json: payload,
    context: "Update schedule failed",
  });
}

export async function deleteSchedule(scheduleId: string): Promise<void> {
  await apiFetch<void>(`/schedules/${scheduleId}`, {
    method: "DELETE",
    context: "Delete schedule failed",
  });
}
