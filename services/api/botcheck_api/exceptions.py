from pydantic import BaseModel

# Named error code constants
SIP_CAPACITY_EXHAUSTED = "sip_capacity_exhausted"
SCHEDULED_RUN_THROTTLED = "scheduled_run_throttled"
PREVIEW_RATE_LIMITED = "preview_rate_limited"
GENERATE_RATE_LIMITED = "generate_rate_limited"
JOB_QUEUE_UNAVAILABLE = "job_queue_unavailable"
JOB_NOT_FOUND = "job_not_found"
HARNESS_UNAVAILABLE = "harness_unavailable"
DESTINATION_IN_USE = "destination_in_use"
AI_SCENARIO_DISPATCH_UNAVAILABLE = "ai_scenario_dispatch_unavailable"
TTS_CACHE_UNAVAILABLE = "tts_cache_unavailable"
TTS_PROVIDER_DISABLED = "tts_provider_disabled"
TTS_PROVIDER_UNCONFIGURED = "tts_provider_unconfigured"
TTS_PROVIDER_UNSUPPORTED = "tts_provider_unsupported"
STT_PROVIDER_DISABLED = "stt_provider_disabled"
STT_PROVIDER_UNCONFIGURED = "stt_provider_unconfigured"
STT_PROVIDER_UNSUPPORTED = "stt_provider_unsupported"
DESTINATIONS_DISABLED = "destinations_disabled"
DESTINATION_NOT_FOUND = "destination_not_found"
DESTINATION_INACTIVE = "destination_inactive"
TRUNK_POOL_NOT_FOUND = "trunk_pool_not_found"
TRUNK_POOL_INACTIVE = "trunk_pool_inactive"
TRUNK_POOL_UNASSIGNED = "trunk_pool_unassigned"
TRUNK_POOL_EMPTY = "trunk_pool_empty"
PRESET_NOT_FOUND = "preset_not_found"
PRESET_NAME_CONFLICT = "preset_name_conflict"
PRESET_INVALID_TRANSPORT_PROFILE = "preset_invalid_transport_profile"
AI_SCENARIO_INACTIVE = "ai_scenario_inactive"
SCENARIO_PACKS_DISABLED = "scenario_packs_disabled"
AI_SCENARIOS_DISABLED = "ai_scenarios_disabled"
AI_SCENARIO_NOT_FOUND = "ai_scenario_not_found"
PACK_NOT_FOUND = "pack_not_found"
PACK_RUN_NOT_FOUND = "pack_run_not_found"
SCHEDULE_NOT_FOUND = "schedule_not_found"
RUN_NOT_FOUND = "run_not_found"
SCENARIO_NOT_FOUND = "scenario_not_found"
AI_PERSONA_NOT_FOUND = "ai_persona_not_found"
AI_SCENARIO_RECORD_NOT_FOUND = "ai_scenario_record_not_found"
RECORDING_NOT_FOUND = "recording_not_found"
TENANT_NOT_FOUND = "tenant_not_found"
TENANT_QUOTA_EXCEEDED = "tenant_quota_exceeded"
PROVIDER_QUOTA_EXCEEDED = "provider_quota_exceeded"
GRAI_EVAL_SUITE_NOT_FOUND = "grai_eval_suite_not_found"
GRAI_EVAL_SUITE_NAME_CONFLICT = "grai_eval_suite_name_conflict"
GRAI_IMPORT_INVALID = "grai_import_invalid"
GRAI_EVAL_RUN_NOT_FOUND = "grai_eval_run_not_found"
GRAI_EVAL_ARTIFACT_NOT_FOUND = "grai_eval_artifact_not_found"
GRAI_INVALID_TRANSPORT_PROFILE = "grai_invalid_transport_profile"
WEBRTC_BOOTSTRAP_FAILED = "webrtc_bootstrap_failed"

_TITLES: dict[int, str] = {
    409: "Conflict",
    429: "Too Many Requests",
    503: "Service Unavailable",
    500: "Internal Server Error",
}


def _default_title(status: int) -> str:
    return _TITLES.get(status, f"HTTP {status}")


class ProblemDetail(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    error_code: str | None = None


class ApiProblem(Exception):
    def __init__(
        self,
        *,
        status: int,
        error_code: str,
        detail: str,
        title: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.error_code = error_code
        self.detail = detail
        self.title = title or _default_title(status)
        self.headers = headers or {}
