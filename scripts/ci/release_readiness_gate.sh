#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"
readonly SOAK_EVIDENCE_MARKER="Soak evidence archive:"
readonly DR_DRILL_SUMMARY_MARKER="DR drill summary:"
readonly ALERT_SIMULATION_MARKER="Alert simulation artifacts:"

API_URL="${BOTCHECK_API_URL:-http://localhost:7700}"
PROM_URL="${BOTCHECK_PROM_URL:-http://localhost:9090}"
API_METRICS_URL="${BOTCHECK_API_METRICS_URL:-${API_URL%/}/metrics}"
JUDGE_METRICS_URL="${BOTCHECK_JUDGE_METRICS_URL:-http://localhost:9101/metrics}"
AGENT_METRICS_URL="${BOTCHECK_AGENT_METRICS_URL:-http://localhost:9102/metrics}"
HTTP_MAX_TIME_S="${BOTCHECK_HTTP_MAX_TIME_S:-10}"
HTTP_CONNECT_TIMEOUT_S="${BOTCHECK_HTTP_CONNECT_TIMEOUT_S:-5}"

CHECK_RUNTIME="${BOTCHECK_CHECK_RUNTIME:-1}"
CHECK_MIGRATIONS="${BOTCHECK_CHECK_MIGRATIONS:-1}"
CHECK_AUDIT_CONVENTIONS="${BOTCHECK_CHECK_AUDIT_CONVENTIONS:-1}"
REQUIRE_AUDIO_GATE="${BOTCHECK_REQUIRE_AUDIO_GATE:-0}"
REQUIRE_PHASE4_EVIDENCE="${BOTCHECK_REQUIRE_PHASE4_EVIDENCE:-0}"
PHASE4_EVIDENCE_ROOT="${BOTCHECK_PHASE4_EVIDENCE_ROOT:-docs/evidence/phase4}"
PHASE4_SOAK_WINDOW="${BOTCHECK_PHASE4_SOAK_WINDOW:-}"
SCENARIO_ID="${BOTCHECK_SCENARIO_ID:-}"
USER_TOKEN="${BOTCHECK_USER_TOKEN:-}"
AUDIO_GATE_SCRIPT="${BOTCHECK_AUDIO_GATE_SCRIPT:-scripts/ci/audio_release_gate.sh}"
AUDIT_CONVENTION_SCRIPT="${BOTCHECK_AUDIT_CONVENTION_SCRIPT:-scripts/ci/check_audit_write_conventions.py}"

PHASE4_EVIDENCE_DIR=""


fct_usage() {
	cat <<EOF
${SCRIPT_NAME}
Phase 4 launch-readiness gate:
  1) migration head check
  2) health and metrics smoke checks
  3) Prometheus rule-load verification
  4) optional full audio release gate

Usage:
  ${SCRIPT_NAME} [options]

Options:
  --api-url <url>            API base URL (default: ${API_URL})
  --prom-url <url>           Prometheus base URL (default: ${PROM_URL})
  --check-runtime <0|1>      Run live migration/smoke/prom/audio checks (default: ${CHECK_RUNTIME})
  --check-migrations <0|1>   Validate alembic current is head in api container (default: ${CHECK_MIGRATIONS})
  --check-audit-conventions <0|1> Run AST guard for audit-write conventions (default: ${CHECK_AUDIT_CONVENTIONS})
  --require-phase4-evidence <0|1> Fail unless item 54 evidence is archived (default: ${REQUIRE_PHASE4_EVIDENCE})
  --phase4-evidence-root <path> Root evidence dir containing <soak-window>/ bundles (default: ${PHASE4_EVIDENCE_ROOT})
  --phase4-soak-window <name> Specific Phase 4 soak-window directory to validate
  --require-audio-gate <0|1> Fail if BOTCHECK_SCENARIO_ID/BOTCHECK_USER_TOKEN are missing (default: ${REQUIRE_AUDIO_GATE})
  --http-max-time <seconds>  Max request time for smoke/rule checks (default: ${HTTP_MAX_TIME_S})
  --http-connect-timeout <seconds> Connect timeout for smoke/rule checks (default: ${HTTP_CONNECT_TIMEOUT_S})
  --scenario-id <id>         Scenario ID for audio gate
  --token <token>            User token for audio gate
  -h, --help                 Show help
EOF
}


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


fct_require_file() {
	local path="${1}"
	local label="${2}"
	if [[ ! -f "${path}" ]]; then
		fct_log "ERROR" "Missing ${label}: ${path}"
		exit 1
	fi
}


fct_require_nonempty_dir() {
	local path="${1}"
	local label="${2}"
	if [[ ! -d "${path}" ]]; then
		fct_log "ERROR" "Missing ${label}: ${path}"
		exit 1
	fi
	if ! find "${path}" -mindepth 1 -maxdepth 1 -print -quit | grep -q .; then
		fct_log "ERROR" "${label} is empty: ${path}"
		exit 1
	fi
}


fct_parse_args() {
	while [[ $# -gt 0 ]]; do
		case "$1" in
		--api-url)
			API_URL="${2:?--api-url requires a value}"
			API_METRICS_URL="${API_URL%/}/metrics"
			shift 2
			;;
		--prom-url)
			PROM_URL="${2:?--prom-url requires a value}"
			shift 2
			;;
		--check-runtime)
			CHECK_RUNTIME="${2:?--check-runtime requires 0|1}"
			shift 2
			;;
		--check-migrations)
			CHECK_MIGRATIONS="${2:?--check-migrations requires 0|1}"
			shift 2
			;;
		--check-audit-conventions)
			CHECK_AUDIT_CONVENTIONS="${2:?--check-audit-conventions requires 0|1}"
			shift 2
			;;
		--require-phase4-evidence)
			REQUIRE_PHASE4_EVIDENCE="${2:?--require-phase4-evidence requires 0|1}"
			shift 2
			;;
		--phase4-evidence-root)
			PHASE4_EVIDENCE_ROOT="${2:?--phase4-evidence-root requires a value}"
			shift 2
			;;
		--phase4-soak-window)
			PHASE4_SOAK_WINDOW="${2:?--phase4-soak-window requires a value}"
			shift 2
			;;
		--require-audio-gate)
			REQUIRE_AUDIO_GATE="${2:?--require-audio-gate requires 0|1}"
			shift 2
			;;
		--http-max-time)
			HTTP_MAX_TIME_S="${2:?--http-max-time requires a value}"
			shift 2
			;;
		--http-connect-timeout)
			HTTP_CONNECT_TIMEOUT_S="${2:?--http-connect-timeout requires a value}"
			shift 2
			;;
		--scenario-id)
			SCENARIO_ID="${2:?--scenario-id requires a value}"
			shift 2
			;;
		--token)
			USER_TOKEN="${2:?--token requires a value}"
			shift 2
			;;
		-h | --help)
			fct_usage
			exit 0
			;;
		*)
			fct_log "ERROR" "Unknown argument: $1"
			fct_usage
			exit 2
			;;
		esac
	done
}


fct_resolve_phase4_evidence_dir() {
	if [[ ! -d "${PHASE4_EVIDENCE_ROOT}" ]]; then
		fct_log "ERROR" "Phase 4 evidence root does not exist: ${PHASE4_EVIDENCE_ROOT}"
		exit 1
	fi

	if [[ -n "${PHASE4_SOAK_WINDOW}" ]]; then
		PHASE4_EVIDENCE_DIR="${PHASE4_EVIDENCE_ROOT%/}/${PHASE4_SOAK_WINDOW}"
		if [[ ! -d "${PHASE4_EVIDENCE_DIR}" ]]; then
			fct_log "ERROR" "Requested Phase 4 soak window not found: ${PHASE4_EVIDENCE_DIR}"
			exit 1
		fi
		return
	fi

	local latest_dir
	latest_dir="$(
		find "${PHASE4_EVIDENCE_ROOT}" -mindepth 1 -maxdepth 1 -type d | LC_ALL=C sort | tail -n 1
	)"
	if [[ -z "${latest_dir}" ]]; then
		fct_log "ERROR" "No Phase 4 evidence bundles found under ${PHASE4_EVIDENCE_ROOT}"
		fct_log "ERROR" "Archive item 54 evidence under docs/evidence/phase4/<soak-window>/ before merging to main"
		exit 1
	fi
	PHASE4_EVIDENCE_DIR="${latest_dir}"
}


fct_require_transcript_marker() {
	local transcript="${1}"
	local marker="${2}"
	local description="${3}"
	if ! grep -Fq "${marker}" "${transcript}"; then
		fct_log "ERROR" "release-readiness-gate transcript missing ${description}: ${transcript}"
		fct_log "ERROR" "Re-run scripts/ci/release_readiness_gate.sh and archive the updated output"
		exit 1
	fi
}


fct_check_phase4_evidence() {
	if [[ "${REQUIRE_PHASE4_EVIDENCE}" != "1" ]]; then
		fct_log "WARN" "Skipping Phase 4 evidence check (REQUIRE_PHASE4_EVIDENCE=${REQUIRE_PHASE4_EVIDENCE})"
		return
	fi

	fct_resolve_phase4_evidence_dir

	local gate_transcript="${PHASE4_EVIDENCE_DIR}/release-readiness-gate.txt"
	local prom_rules="${PHASE4_EVIDENCE_DIR}/prom-rules.json"
	local backup_restore_dir="${PHASE4_EVIDENCE_DIR}/backup-restore"
	local backup_restore_summary="${backup_restore_dir}/summary.env"
	local alert_simulation_dir="${PHASE4_EVIDENCE_DIR}/alert-simulation"
	local day

	for day in 1 2 3 4 5 6 7; do
		fct_require_file "${PHASE4_EVIDENCE_DIR}/day-${day}.md" "Phase 4 soak day ${day} snapshot"
	done
	fct_require_file "${gate_transcript}" "archived release-readiness gate transcript"
	fct_require_file "${prom_rules}" "Prometheus rules snapshot"
	fct_require_nonempty_dir "${backup_restore_dir}" "backup-restore drill artifact directory"
	fct_require_file "${backup_restore_summary}" "backup-restore summary"
	fct_require_nonempty_dir "${alert_simulation_dir}" "alert-simulation artifact directory"
	fct_require_transcript_marker "${gate_transcript}" "${SOAK_EVIDENCE_MARKER}" "soak evidence reference"
	fct_require_transcript_marker "${gate_transcript}" "${DR_DRILL_SUMMARY_MARKER}" "DR drill reference"
	fct_require_transcript_marker "${gate_transcript}" "${ALERT_SIMULATION_MARKER}" "alert simulation reference"

	fct_log "INFO" "${SOAK_EVIDENCE_MARKER} ${PHASE4_EVIDENCE_DIR}"
	fct_log "INFO" "Soak gate transcript: ${gate_transcript}"
	fct_log "INFO" "Prometheus rule snapshot: ${prom_rules}"
	fct_log "INFO" "${DR_DRILL_SUMMARY_MARKER} ${backup_restore_summary}"
	fct_log "INFO" "${ALERT_SIMULATION_MARKER} ${alert_simulation_dir}"
}


fct_http_smoke() {
	local url="${1}"
	local label="${2}"
	if ! curl -fsS \
		--max-time "${HTTP_MAX_TIME_S}" \
		--connect-timeout "${HTTP_CONNECT_TIMEOUT_S}" \
		"${url}" >/dev/null; then
		fct_log "ERROR" "Smoke check failed for ${label}: ${url}"
		exit 1
	fi
	fct_log "INFO" "Smoke check passed for ${label}"
}


fct_check_migrations_head() {
	if [[ "${CHECK_MIGRATIONS}" != "1" ]]; then
		fct_log "WARN" "Skipping migration head check (CHECK_MIGRATIONS=${CHECK_MIGRATIONS})"
		return
	fi

	fct_require_command "docker"

	if ! docker compose ps --status running api 2>/dev/null | grep -q "api"; then
		fct_log "ERROR" "API container is not running; cannot validate alembic current=head"
		exit 1
	fi

	local current
	current="$(
		docker compose exec -T api bash -c \
			"cd /app/services/api && uv run alembic current" 2>/dev/null || true
	)"
	if [[ -z "${current}" ]]; then
		fct_log "ERROR" "Failed to read alembic current revision from api container"
		exit 1
	fi

	if ! grep -q "(head)" <<<"${current}"; then
		fct_log "ERROR" "Alembic current is not at head"
		printf '%s\n' "${current}" >&2
		exit 1
	fi

	fct_log "INFO" "Alembic current revision is at head"
}


fct_require_prom_rule() {
	local rules_json="${1}"
	local rule_name="${2}"
	if ! jq -e --arg name "${rule_name}" '
		.data.groups[].rules[] | select(.name == $name)
	' >/dev/null <<<"${rules_json}"; then
		fct_log "ERROR" "Prometheus rule not loaded: ${rule_name}"
		exit 1
	fi
}


fct_check_prometheus_rules() {
	local rules_json
	rules_json="$(
		curl -fsS \
			--max-time "${HTTP_MAX_TIME_S}" \
			--connect-timeout "${HTTP_CONNECT_TIMEOUT_S}" \
			"${PROM_URL%/}/api/v1/rules"
	)"
	if ! jq -e '.status == "success"' >/dev/null <<<"${rules_json}"; then
		fct_log "ERROR" "Prometheus /api/v1/rules returned non-success status"
		exit 1
	fi

	fct_require_prom_rule "${rules_json}" "BotCheckAPIAvailabilityLow"
	fct_require_prom_rule "${rules_json}" "BotCheckRunSuccessRateLow"
	fct_require_prom_rule "${rules_json}" "BotCheckJudgeLatencyP95High"
	fct_require_prom_rule "${rules_json}" "BotCheckJudgeQueueLagHigh"
	fct_require_prom_rule "${rules_json}" "BotCheckSIPTelephonyDown"
	fct_require_prom_rule "${rules_json}" "BotCheckProviderCircuitOpen"
	fct_require_prom_rule "${rules_json}" "BotCheckProviderCircuitRejectionsHigh"
	fct_log "INFO" "Prometheus SLO rule load check passed"
}


fct_check_audit_write_conventions() {
	if [[ "${CHECK_AUDIT_CONVENTIONS}" != "1" ]]; then
		fct_log "WARN" "Skipping audit-write convention check (CHECK_AUDIT_CONVENTIONS=${CHECK_AUDIT_CONVENTIONS})"
		return
	fi

	fct_require_command "python3"
	if [[ ! -f "${AUDIT_CONVENTION_SCRIPT}" ]]; then
		fct_log "ERROR" "Audit convention script missing: ${AUDIT_CONVENTION_SCRIPT}"
		exit 1
	fi

	if ! python3 "${AUDIT_CONVENTION_SCRIPT}" --root services/api/botcheck_api; then
		fct_log "ERROR" "Audit-write convention check failed"
		exit 1
	fi

	fct_log "INFO" "Audit-write convention check passed"
}


fct_run_optional_audio_gate() {
	if [[ -n "${SCENARIO_ID}" && -n "${USER_TOKEN}" ]]; then
		if [[ ! -x "${AUDIO_GATE_SCRIPT}" ]]; then
			fct_log "ERROR" "Audio gate script not executable: ${AUDIO_GATE_SCRIPT}"
			exit 1
		fi
		fct_log "INFO" "Running audio release gate scenario=${SCENARIO_ID}"
		"${AUDIO_GATE_SCRIPT}" \
			--api-url "${API_URL}" \
			--scenario-id "${SCENARIO_ID}" \
			--token "${USER_TOKEN}"
		fct_log "INFO" "Audio release gate passed"
		return
	fi

	if [[ "${REQUIRE_AUDIO_GATE}" == "1" ]]; then
		fct_log "ERROR" "Audio gate required but BOTCHECK_SCENARIO_ID/BOTCHECK_USER_TOKEN missing"
		exit 1
	fi
	fct_log "WARN" "Skipping audio gate (set BOTCHECK_SCENARIO_ID + BOTCHECK_USER_TOKEN to enable)"
}


fct_check_runtime() {
	if [[ "${CHECK_RUNTIME}" != "1" ]]; then
		fct_log "WARN" "Skipping live runtime checks (CHECK_RUNTIME=${CHECK_RUNTIME})"
		return
	fi

	fct_require_command "curl"
	fct_require_command "jq"
	fct_check_migrations_head
	fct_http_smoke "${API_URL%/}/health" "api-health"
	fct_http_smoke "${API_METRICS_URL}" "api-metrics"
	fct_http_smoke "${JUDGE_METRICS_URL}" "judge-metrics"
	fct_http_smoke "${AGENT_METRICS_URL}" "agent-metrics"
	fct_http_smoke "${PROM_URL%/}/-/healthy" "prometheus-health"
	fct_check_prometheus_rules
	fct_check_audit_write_conventions
	fct_run_optional_audio_gate
}


fct_main() {
	fct_parse_args "$@"
	fct_check_phase4_evidence
	fct_check_runtime

	fct_log "INFO" "Phase 4 launch-readiness gate passed"
}


fct_main "$@"
