#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"

API_URL="${BOTCHECK_API_URL:-http://localhost:7700}"
USER_TOKEN="${BOTCHECK_USER_TOKEN:-}"
SCENARIO_ID="${BOTCHECK_SCENARIO_ID:-}"
BOT_ENDPOINT="${BOTCHECK_BOT_ENDPOINT:-}"
GATE_TIMEOUT_S="${BOTCHECK_GATE_TIMEOUT_S:-900}"
POLL_INTERVAL_S="${BOTCHECK_GATE_POLL_S:-5}"


fct_usage() {
	cat <<EOF
${SCRIPT_NAME}
Create a run and block until /runs/{id}/gate returns passed or blocked.

Usage:
  ${SCRIPT_NAME} --scenario-id <id> --token <token> [options]

Options:
  --api-url <url>          BotCheck API base URL (default: ${API_URL})
  --scenario-id <id>       Scenario ID to execute
  --token <token>          User bearer token for API auth
  --bot-endpoint <uri>     Optional bot endpoint override
  --timeout-s <seconds>    Max wait for gate result (default: ${GATE_TIMEOUT_S})
  --poll-s <seconds>       Poll interval for gate checks (default: ${POLL_INTERVAL_S})
  -h, --help               Show help and exit
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


fct_parse_args() {
	while [[ $# -gt 0 ]]; do
		case "$1" in
		--api-url)
			API_URL="${2:?--api-url requires a value}"
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
		--bot-endpoint)
			BOT_ENDPOINT="${2:?--bot-endpoint requires a value}"
			shift 2
			;;
		--timeout-s)
			GATE_TIMEOUT_S="${2:?--timeout-s requires a value}"
			shift 2
			;;
		--poll-s)
			POLL_INTERVAL_S="${2:?--poll-s requires a value}"
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


fct_http_request() {
	local method="${1}"
	local path="${2}"
	local payload="${3:-}"
	local url="${API_URL%/}${path}"

	if [[ -n "${payload}" ]]; then
		curl -sS \
			-X "${method}" \
			-H "Authorization: Bearer ${USER_TOKEN}" \
			-H "Content-Type: application/json" \
			--data "${payload}" \
			"${url}" \
			-w $'\n%{http_code}'
	else
		curl -sS \
			-X "${method}" \
			-H "Authorization: Bearer ${USER_TOKEN}" \
			"${url}" \
			-w $'\n%{http_code}'
	fi
}


fct_create_run() {
	local payload=""
	if [[ -n "${BOT_ENDPOINT}" ]]; then
		payload="$(jq -cn --arg scenario_id "${SCENARIO_ID}" --arg bot_endpoint "${BOT_ENDPOINT}" '{scenario_id: $scenario_id, bot_endpoint: $bot_endpoint}')"
	else
		payload="$(jq -cn --arg scenario_id "${SCENARIO_ID}" '{scenario_id: $scenario_id}')"
	fi

	local response
	response="$(fct_http_request "POST" "/runs/" "${payload}")"
	local body="${response%$'\n'*}"
	local status="${response##*$'\n'}"

	if [[ "${status}" != "202" ]]; then
		fct_log "ERROR" "Run creation failed with HTTP ${status}"
		printf '%s\n' "${body}" >&2
		exit 1
	fi

	local run_id
	run_id="$(printf '%s' "${body}" | jq -r '.run_id // empty')"
	if [[ -z "${run_id}" ]]; then
		fct_log "ERROR" "Run creation response did not contain run_id"
		printf '%s\n' "${body}" >&2
		exit 1
	fi

	printf '%s\n' "${run_id}"
}


fct_wait_for_gate() {
	local run_id="${1}"
	local deadline=$((SECONDS + GATE_TIMEOUT_S))

	while ((SECONDS < deadline)); do
		local response
		response="$(fct_http_request "GET" "/runs/${run_id}/gate")"
		local body="${response%$'\n'*}"
		local status="${response##*$'\n'}"

		if [[ "${status}" == "202" ]]; then
			fct_log "INFO" "Run ${run_id} still in progress; polling again in ${POLL_INTERVAL_S}s"
			sleep "${POLL_INTERVAL_S}"
			continue
		fi

		if [[ "${status}" != "200" ]]; then
			fct_log "ERROR" "Gate request failed with HTTP ${status}"
			printf '%s\n' "${body}" >&2
			exit 1
		fi

		local gate_result
		gate_result="$(printf '%s' "${body}" | jq -r '.gate_result // empty')"
		local summary
		summary="$(printf '%s' "${body}" | jq -r '.summary // ""')"
		fct_log "INFO" "Run ${run_id} gate_result=${gate_result} summary=${summary}"

		if [[ "${gate_result}" == "passed" ]]; then
			return 0
		fi

		fct_log "ERROR" "Release audio gate blocked for run ${run_id}"
		printf '%s\n' "${body}" >&2
		return 1
	done

	fct_log "ERROR" "Timed out waiting for gate result after ${GATE_TIMEOUT_S}s"
	return 1
}


fct_main() {
	fct_parse_args "$@"
	fct_require_command "curl"
	fct_require_command "jq"

	if [[ -z "${SCENARIO_ID}" ]]; then
		fct_log "ERROR" "--scenario-id is required"
		exit 2
	fi
	if [[ -z "${USER_TOKEN}" ]]; then
		fct_log "ERROR" "--token is required"
		exit 2
	fi

	local run_id
	run_id="$(fct_create_run)"
	fct_log "INFO" "Created run ${run_id}; waiting for gate decision"
	fct_wait_for_gate "${run_id}"
	fct_log "INFO" "Release audio gate passed for run ${run_id}"
}


fct_main "$@"
