import { ApiHttpError } from "./fetcher";

type ErrorTone = "info" | "warn" | "error";
interface ErrorMapping {
  message: string;
  tone: ErrorTone;
}

const BY_CODE: Record<string, ErrorMapping> = {
  sip_capacity_exhausted: {
    message: "All calling slots are busy — try again in a moment.",
    tone: "warn",
  },
  scheduled_run_throttled: {
    message: "Scheduled run skipped — SIP capacity was full.",
    tone: "warn",
  },
  preview_rate_limited: {
    message: "Audio preview rate limit reached — try again soon.",
    tone: "warn",
  },
  generate_rate_limited: {
    message: "Scenario generation rate limit — try again later.",
    tone: "warn",
  },
  job_queue_unavailable: {
    message: "Job queue is temporarily unavailable.",
    tone: "warn",
  },
  job_not_found: {
    message: "The requested job no longer exists.",
    tone: "warn",
  },
  harness_unavailable: {
    message: "Harness worker is unavailable. Try again shortly.",
    tone: "warn",
  },
  destination_in_use: {
    message: "Destination is in use by active schedules or pack runs. Remove references first.",
    tone: "warn",
  },
  destinations_disabled: {
    message: "Transport profiles are disabled on this instance.",
    tone: "warn",
  },
  destination_not_found: {
    message: "The selected transport profile no longer exists.",
    tone: "warn",
  },
  destination_inactive: {
    message: "The selected transport profile is inactive.",
    tone: "warn",
  },
  preset_not_found: {
    message: "The selected playground preset no longer exists.",
    tone: "warn",
  },
  preset_name_conflict: {
    message: "A playground preset with that name already exists.",
    tone: "warn",
  },
  preset_invalid_transport_profile: {
    message: "Direct HTTP presets require an active HTTP transport profile.",
    tone: "warn",
  },
  ai_scenario_inactive: {
    message: "The selected AI scenario is inactive.",
    tone: "warn",
  },
  scenario_packs_disabled: {
    message: "Scenario packs are disabled on this instance.",
    tone: "warn",
  },
  ai_scenarios_disabled: {
    message: "AI scenarios are disabled on this instance.",
    tone: "warn",
  },
  ai_scenario_not_found: {
    message: "The selected AI scenario no longer exists.",
    tone: "warn",
  },
  pack_not_found: {
    message: "The selected pack no longer exists.",
    tone: "warn",
  },
  pack_run_not_found: {
    message: "The selected pack run no longer exists.",
    tone: "warn",
  },
  schedule_not_found: {
    message: "The selected schedule no longer exists.",
    tone: "warn",
  },
  run_not_found: {
    message: "The selected run no longer exists.",
    tone: "warn",
  },
  scenario_not_found: {
    message: "The selected scenario no longer exists.",
    tone: "warn",
  },
  ai_persona_not_found: {
    message: "The selected AI persona no longer exists.",
    tone: "warn",
  },
  ai_scenario_record_not_found: {
    message: "The selected AI scenario record no longer exists.",
    tone: "warn",
  },
  recording_not_found: {
    message: "Recording not found.",
    tone: "warn",
  },
  ai_scenario_dispatch_unavailable: {
    message: "AI scenario dispatch is not available yet.",
    tone: "warn",
  },
  ai_caller_unavailable: {
    message: "AI caller runtime is unavailable for this run.",
    tone: "warn",
  },
  tts_cache_unavailable: {
    message: "TTS cache is not ready for this scenario. Rebuild cache and retry.",
    tone: "warn",
  },
  trunk_pool_not_found: {
    message: "The SIP trunk pool configured on this transport profile no longer exists. Edit the transport profile and re-assign a pool.",
    tone: "error",
  },
  trunk_pool_inactive: {
    message: "The SIP trunk pool configured on this transport profile is inactive. Re-activate the pool or assign a different one.",
    tone: "warn",
  },
  trunk_pool_unassigned: {
    message: "The SIP trunk pool configured on this transport profile is not assigned to your tenant. Ask an admin to assign the pool.",
    tone: "error",
  },
  trunk_pool_empty: {
    message: "The SIP trunk pool has no active trunks available. Ask an admin to add trunks to the pool.",
    tone: "error",
  },
  reaper_force_closed: {
    message: "Run exceeded its max duration and was force-closed.",
    tone: "warn",
  },
  operator_aborted: {
    message: "Run was stopped by an operator.",
    tone: "warn",
  },
};

const BY_STATUS: Partial<Record<number, ErrorMapping>> = {
  401: { message: "Your session has expired. Please log in again.", tone: "error" },
  403: { message: "You don't have permission to do that.", tone: "error" },
  404: { message: "The requested resource was not found.", tone: "error" },
  409: { message: "A conflict occurred. Please refresh and try again.", tone: "warn" },
  422: {
    message: "The request contained invalid data. Check inputs and retry.",
    tone: "error",
  },
  429: { message: "Too many requests — please slow down.", tone: "warn" },
  500: { message: "An unexpected server error occurred.", tone: "error" },
  503: { message: "Service temporarily unavailable. Try again shortly.", tone: "warn" },
};

export function mapApiError(
  error: unknown,
  fallback = "An error occurred."
): ErrorMapping {
  if (error instanceof ApiHttpError) {
    if (error.errorCode) {
      const mapped = BY_CODE[error.errorCode];
      if (mapped) return mapped;
    }
    const byStatus = BY_STATUS[error.status];
    if (byStatus) return byStatus;
    const detail = error.problem?.detail ?? error.body;
    return { message: detail || fallback, tone: "error" };
  }
  const message = error instanceof Error ? error.message : fallback;
  return { message, tone: "error" };
}
