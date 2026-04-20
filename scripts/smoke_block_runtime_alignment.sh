#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"
readonly SCRIPT_DIR="$(cd "${0%/*}" >/dev/null 2>&1 && pwd -P)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd -P)"
readonly DEFAULT_SERVICES=("api" "agent" "cache-worker" "judge")

API_URL="${BOTCHECK_API_URL:-http://localhost:7700}"
USER_TOKEN="${BOTCHECK_USER_TOKEN:-${BOTCHECK_TOKEN:-}}"
WAIT_SCENARIO_ID="${BOTCHECK_WAIT_SCENARIO_ID:-}"
TIME_ROUTE_SCENARIO_ID="${BOTCHECK_TIME_ROUTE_SCENARIO_ID:-}"
TIMEOUT_S="${TIMEOUT_S:-90}"
POLL_S="${POLL_S:-3}"
SKIP_RESTART=0

fct_usage() {
	cat <<EOF_USAGE
${SCRIPT_NAME}
Restart long-lived block-runtime services, rebuild cache for one wait scenario and
one time_route scenario, and poll until both report cache_status=warm.

Usage:
  ${SCRIPT_NAME} --user-token <token> --wait-scenario-id <id> --time-route-scenario-id <id> [options]

Options:
  --api-url <url>                 BotCheck API base URL (default: ${API_URL})
  --user-token <token>            BotCheck bearer token
  --wait-scenario-id <id>         Scenario id for a canonical wait scenario
  --time-route-scenario-id <id>   Scenario id for a canonical time_route scenario
  --timeout-s <seconds>           Cache warm timeout per scenario (default: ${TIMEOUT_S})
  --poll-s <seconds>              Poll interval while waiting for warm cache (default: ${POLL_S})
  --skip-restart                  Skip docker compose restart and only run API/cache checks
  -h, --help                      Show help and exit

Environment:
  BOTCHECK_API_URL
  BOTCHECK_USER_TOKEN or BOTCHECK_TOKEN
  BOTCHECK_WAIT_SCENARIO_ID
  BOTCHECK_TIME_ROUTE_SCENARIO_ID
  TIMEOUT_S
  POLL_S

What this script does:
  1. Restart api/agent/cache-worker/judge (unless --skip-restart).
  2. Wait for API /health to return 200.
  3. POST /scenarios/{id}/cache/rebuild for the wait and time_route scenarios.
  4. Poll /scenarios/{id} until cache_status == "warm" for both.

Manual follow-up after the script passes:
  - Save and run both scenarios from the builder.
  - Confirm no union_tag_invalid errors in api/agent/cache-worker/judge logs.
  - Confirm transcript ordering is correct.
  - Confirm the selected time_route path matches the configured clock window.
EOF_USAGE
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

fct_parse_args() {
	while [[ $# -gt 0 ]]; do
		case "$1" in
		--api-url)
			API_URL="${2:?--api-url requires a value}"
			shift 2
			;;
		--user-token)
			USER_TOKEN="${2:?--user-token requires a value}"
			shift 2
			;;
		--wait-scenario-id)
			WAIT_SCENARIO_ID="${2:?--wait-scenario-id requires a value}"
			shift 2
			;;
		--time-route-scenario-id)
			TIME_ROUTE_SCENARIO_ID="${2:?--time-route-scenario-id requires a value}"
			shift 2
			;;
		--timeout-s)
			TIMEOUT_S="${2:?--timeout-s requires a value}"
			shift 2
			;;
		--poll-s)
			POLL_S="${2:?--poll-s requires a value}"
			shift 2
			;;
		--skip-restart)
			SKIP_RESTART=1
			shift
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

fct_restart_services() {
	if [[ "${SKIP_RESTART}" -eq 1 ]]; then
		fct_log "INFO" "Skipping docker compose restart"
		return
	fi

	fct_log "INFO" "Restarting long-lived Python services: ${DEFAULT_SERVICES[*]}"
	(
		cd "${REPO_ROOT}" &&
			docker compose restart "${DEFAULT_SERVICES[@]}"
	)
}

fct_wait_for_api_health() {
	local deadline=$((SECONDS + TIMEOUT_S))
	local health_url="${API_URL%/}/health"

	fct_log "INFO" "Waiting for API health at ${health_url}"
	while ((SECONDS < deadline)); do
		if curl -fsS "${health_url}" >/dev/null 2>&1; then
			fct_log "INFO" "API is healthy"
			return
		fi
		sleep "${POLL_S}"
	done

	fct_log "ERROR" "Timed out waiting for API health"
	exit 1
}

fct_post_cache_rebuild() {
	local scenario_id="${1}"

	fct_log "INFO" "Requesting cache rebuild for scenario ${scenario_id}"
	curl -fsS \
		-X POST \
		-H "Authorization: Bearer ${USER_TOKEN}" \
		"${API_URL%/}/scenarios/${scenario_id}/cache/rebuild" >/dev/null
}

fct_get_cache_status() {
	local scenario_id="${1}"
	local body=""

	body="$(curl -fsS \
		-H "Authorization: Bearer ${USER_TOKEN}" \
		"${API_URL%/}/scenarios/${scenario_id}" 2>/dev/null)" || {
		echo "error"
		return
	}
	printf '%s' "${body}" | jq -r '.cache_status' 2>/dev/null || echo "error"
}

fct_wait_for_cache_warm() {
	local scenario_id="${1}"
	local deadline=$((SECONDS + TIMEOUT_S))
	local status=""

	fct_log "INFO" "Waiting for scenario ${scenario_id} cache_status=warm"
	while ((SECONDS < deadline)); do
		status="$(fct_get_cache_status "${scenario_id}")"
		case "${status}" in
		warm)
			fct_log "INFO" "Scenario ${scenario_id} cache is warm"
			return
			;;
		warming | partial | cold)
			fct_log "INFO" "Scenario ${scenario_id} cache_status=${status}; polling again"
			sleep "${POLL_S}"
			;;
		error)
			fct_log "WARN" "Transient API error for ${scenario_id}; retrying"
			sleep "${POLL_S}"
			;;
		*)
			fct_log "ERROR" "Unexpected cache_status for ${scenario_id}: ${status}"
			exit 1
			;;
		esac
	done

	fct_log "ERROR" "Timed out waiting for ${scenario_id} cache to become warm (last status: ${status})"
	exit 1
}

fct_print_manual_follow_up() {
	cat >&2 <<EOF_NEXT

Next manual checks:
  1. Open the builder and save both scenarios:
     - ${WAIT_SCENARIO_ID}
     - ${TIME_ROUTE_SCENARIO_ID}
  2. Run both scenarios.
  3. Confirm:
     - no union_tag_invalid errors in docker compose logs for api/agent/cache-worker/judge
     - transcript ordering is correct
     - the selected time_route path matches the configured clock window

Useful log command:
  docker compose logs -f api agent cache-worker judge
EOF_NEXT
}

fct_main() {
	fct_parse_args "$@"
	fct_require_command "curl"
	fct_require_command "docker"
	fct_require_command "jq"

	[[ -n "${USER_TOKEN}" ]] || {
		fct_log "ERROR" "--user-token is required (or set BOTCHECK_USER_TOKEN / BOTCHECK_TOKEN)"
		exit 2
	}
	[[ -n "${WAIT_SCENARIO_ID}" ]] || {
		fct_log "ERROR" "--wait-scenario-id is required"
		exit 2
	}
	[[ -n "${TIME_ROUTE_SCENARIO_ID}" ]] || {
		fct_log "ERROR" "--time-route-scenario-id is required"
		exit 2
	}

	fct_restart_services
	fct_wait_for_api_health
	fct_post_cache_rebuild "${WAIT_SCENARIO_ID}"
	fct_post_cache_rebuild "${TIME_ROUTE_SCENARIO_ID}"
	fct_wait_for_cache_warm "${WAIT_SCENARIO_ID}"
	fct_wait_for_cache_warm "${TIME_ROUTE_SCENARIO_ID}"
	fct_print_manual_follow_up
}

fct_main "$@"
