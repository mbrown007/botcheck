#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"
UV_BIN="${UV_BIN:-uv}"
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"
BOTCHECK_REPO_ROOT="${BOTCHECK_REPO_ROOT:-}"

fct_log() {
	local level="${1}"
	shift
	printf '%s [%s] %s\n' "${level}" "${SCRIPT_NAME}" "$*" >&2
}

fct_require_command() {
	local cmd="${1}"
	if ! command -v "${cmd}" >/dev/null 2>&1; then
		fct_log "ERROR" "Missing required command: ${cmd}"
		exit 2
	fi
}

fct_run_pytest() {
	local label="${1}"
	shift
	fct_log "INFO" "Running ${label}"
	"${UV_BIN}" run --project services/api pytest -q "$@"
}

fct_main() {
	fct_require_command "${UV_BIN}"
	export UV_CACHE_DIR
	if [[ -z "${BOTCHECK_REPO_ROOT}" ]]; then
		BOTCHECK_REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
	fi
	export BOTCHECK_REPO_ROOT

	fct_run_pytest "pack feature gate + CRUD + idempotent trigger" \
		services/api/tests/test_packs.py::test_packs_routes_return_503_when_feature_disabled \
		services/api/tests/test_packs.py::test_pack_crud_lifecycle \
		services/api/tests/test_packs.py::test_run_pack_reuses_active_snapshot_when_idempotency_key_matches

	fct_run_pytest "dispatch fan-out + capacity backoff + version drift handling" \
		services/api/tests/test_packs.py::test_internal_dispatch_pack_run_transitions_pending_to_running \
		services/api/tests/test_packs.py::test_internal_dispatch_pack_capacity_backoff_limits_dispatched_children \
		services/api/tests/test_packs.py::test_internal_dispatch_mixed_version_mismatch_and_successful_dispatch

	fct_run_pytest "terminal fan-in + detail heatmap + failure-priority children" \
		services/api/tests/test_packs.py::test_judge_patch_updates_pack_run_aggregate_and_heatmap \
		services/api/tests/test_packs.py::test_pack_run_detail_exposes_previous_heatmap_for_trend \
		services/api/tests/test_packs.py::test_pack_run_children_failures_only_and_failure_priority_pagination

	fct_run_pytest "pack-run cancel state machine" \
		services/api/tests/test_packs.py::test_cancel_pack_run_from_pending_prevents_dispatch \
		services/api/tests/test_packs.py::test_cancel_pack_run_from_running_marks_cancelled \
		services/api/tests/test_packs.py::test_dispatch_stops_when_pack_run_cancelled_mid_fanout \
		services/api/tests/test_packs.py::test_cancel_pack_run_returns_409_for_terminal_pack_run

	fct_run_pytest "schedule pack target routing + scheduler attribution" \
		services/api/tests/test_schedules.py::TestSchedules::test_create_pack_target_schedule_returns_201 \
		services/api/tests/test_schedules.py::TestSchedules::test_patch_schedule_can_switch_from_scenario_target_to_pack_target \
		services/api/tests/test_schedules.py::TestSchedules::test_dispatch_due_pack_target_enqueues_pack_dispatch \
		services/api/tests/test_schedules.py::TestSchedules::test_dispatch_due_pack_target_child_runs_keep_scheduled_trigger_source

	fct_log "INFO" "Phase 9 matrix checks passed"
}

fct_main "$@"
