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
	"${UV_BIN}" run pytest -q "$@"
}


fct_main() {
	fct_require_command "${UV_BIN}"
	export UV_CACHE_DIR
	if [[ -z "${BOTCHECK_REPO_ROOT}" ]]; then
		BOTCHECK_REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
	fi
	export BOTCHECK_REPO_ROOT

	fct_run_pytest "linear parity + branching traversal + classifier" \
		services/agent/tests/test_graph.py \
		services/agent/tests/test_branch_classifier.py \
		services/agent/tests/test_run_scenario_cache.py \
		services/agent/tests/test_final_ack.py

	fct_run_pytest "loop guard + branch snippet redaction pipeline" \
		services/api/unit_tests/test_runs_loop_guard.py \
		services/api/unit_tests/test_runs_branch_snippet.py

	fct_run_pytest "fail-closed branching payload contract" \
		services/judge/tests/test_worker.py::test_payload_validation_rejects_branching_with_empty_taken_path_steps \
		services/judge/tests/test_worker.py::test_judge_run_invalid_branching_payload_applies_fail_closed_patch

	fct_run_pytest "multi-visit turn.expect fixtures + path-scoping guardrail" \
		services/judge/tests/test_deterministic.py::TestForbiddenPhrases::test_multi_visit_expect_all_visits_pass \
		services/judge/tests/test_deterministic.py::TestForbiddenPhrases::test_multi_visit_expect_fails_when_one_visit_contains_forbidden_phrase \
		services/judge/tests/test_deterministic.py::TestForbiddenPhrases::test_path_scoping_hardening_registry_for_turn_expectations

	fct_run_pytest "branching all-arms pre-warm cache coverage" \
		services/judge/tests/test_cache_worker.py::test_warm_tts_cache_branching_scenario_precaches_all_harness_arms

	fct_log "INFO" "Phase 5 matrix checks passed"
}


fct_main "$@"
