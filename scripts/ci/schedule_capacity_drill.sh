#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"

API_URL="${BOTCHECK_API_URL:-http://localhost:7700}"
SCHEDULER_TOKEN="${BOTCHECK_SCHEDULER_TOKEN:-}"
SCENARIO_ID="${BOTCHECK_SCENARIO_ID:-}"
BURST_COUNT="${BOTCHECK_BURST_COUNT:-10}"
EXPECTED_ACCEPTED="${BOTCHECK_EXPECT_ACCEPTED:-5}"
EXPECTED_THROTTLED="${BOTCHECK_EXPECT_THROTTLED:-}"
POLL_GATES="${BOTCHECK_CAPACITY_POLL_GATES:-false}"
GATE_TIMEOUT_S="${BOTCHECK_CAPACITY_GATE_TIMEOUT_S:-300}"
GATE_POLL_S="${BOTCHECK_CAPACITY_GATE_POLL_S:-5}"


fct_usage() {
	cat <<EOF
${SCRIPT_NAME}
Fire a scheduled run burst and verify SIP capacity throttling behavior.

Usage:
  ${SCRIPT_NAME} --scenario-id <id> --scheduler-token <token> [options]

Options:
  --api-url <url>             BotCheck API base URL (default: ${API_URL})
  --scenario-id <id>          Scenario ID for scheduled runs
  --scheduler-token <token>   Scheduler service bearer token
  --burst <n>                 Number of scheduled create requests (default: ${BURST_COUNT})
  --expect-accepted <n>       Expected HTTP 202 count (default: ${EXPECTED_ACCEPTED})
  --expect-throttled <n>      Expected HTTP 429 count (default: burst-accepted)
  --poll-gates                Poll /runs/{id}/gate for accepted runs until terminal
  --gate-timeout-s <seconds>  Gate polling timeout when --poll-gates is set
  --gate-poll-s <seconds>     Gate polling interval when --poll-gates is set
  -h, --help                  Show help and exit
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
		--scheduler-token)
			SCHEDULER_TOKEN="${2:?--scheduler-token requires a value}"
			shift 2
			;;
		--burst)
			BURST_COUNT="${2:?--burst requires a value}"
			shift 2
			;;
		--expect-accepted)
			EXPECTED_ACCEPTED="${2:?--expect-accepted requires a value}"
			shift 2
			;;
		--expect-throttled)
			EXPECTED_THROTTLED="${2:?--expect-throttled requires a value}"
			shift 2
			;;
		--poll-gates)
			POLL_GATES="true"
			shift
			;;
		--gate-timeout-s)
			GATE_TIMEOUT_S="${2:?--gate-timeout-s requires a value}"
			shift 2
			;;
		--gate-poll-s)
			GATE_POLL_S="${2:?--gate-poll-s requires a value}"
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


fct_wait_for_gate() {
	local run_id="${1}"
	local deadline=$((SECONDS + GATE_TIMEOUT_S))
	while ((SECONDS < deadline)); do
		local response body status
		response="$(curl -sS \
			-H "Authorization: Bearer ${SCHEDULER_TOKEN}" \
			"${API_URL%/}/runs/${run_id}/gate" \
			-w $'\n%{http_code}')"
		body="${response%$'\n'*}"
		status="${response##*$'\n'}"
		if [[ "${status}" == "202" ]]; then
			sleep "${GATE_POLL_S}"
			continue
		fi
		if [[ "${status}" != "200" ]]; then
			fct_log "ERROR" "Gate check failed for ${run_id} with status ${status}: ${body}"
			return 1
		fi
		local gate_result
		gate_result="$(printf '%s' "${body}" | jq -r '.gate_result // empty')"
		fct_log "INFO" "Run ${run_id} gate_result=${gate_result}"
		return 0
	done
	fct_log "ERROR" "Timed out waiting for gate on ${run_id}"
	return 1
}


fct_main() {
	fct_parse_args "$@"
	fct_require_command "curl"
	fct_require_command "jq"

	[[ -n "${SCENARIO_ID}" ]] || { fct_log "ERROR" "--scenario-id is required"; exit 2; }
	[[ -n "${SCHEDULER_TOKEN}" ]] || { fct_log "ERROR" "--scheduler-token is required"; exit 2; }

	if [[ -z "${EXPECTED_THROTTLED}" ]]; then
		EXPECTED_THROTTLED="$((BURST_COUNT - EXPECTED_ACCEPTED))"
	fi

	local tmp
	tmp="$(mktemp -d)"
	trap 'rm -rf "${tmp}"' EXIT

	fct_log "INFO" "Dispatching burst: count=${BURST_COUNT}, expect_202=${EXPECTED_ACCEPTED}, expect_429=${EXPECTED_THROTTLED}"

	local i
	for i in $(seq 1 "${BURST_COUNT}"); do
		(
			local schedule_id payload response body status
			schedule_id="capacity-${i}"
			payload="$(jq -cn --arg sid "${SCENARIO_ID}" --arg schedule_id "${schedule_id}" --arg trig "capacity-drill" '{scenario_id: $sid, schedule_id: $schedule_id, triggered_by: $trig}')"
			response="$(curl -sS \
				-X POST \
				-H "Authorization: Bearer ${SCHEDULER_TOKEN}" \
				-H "Content-Type: application/json" \
				--data "${payload}" \
				"${API_URL%/}/runs/scheduled" \
				-w $'\n%{http_code}')"
			body="${response%$'\n'*}"
			status="${response##*$'\n'}"
			printf '%s\n' "${status}" >"${tmp}/${i}.status"
			printf '%s\n' "${body}" >"${tmp}/${i}.body"
		) &
	done
	wait

	local accepted throttled other
	accepted="$(grep -Rxc "202" "${tmp}"/*.status || true)"
	throttled="$(grep -Rxc "429" "${tmp}"/*.status || true)"
	other="$((BURST_COUNT - accepted - throttled))"
	fct_log "INFO" "Burst result: accepted=${accepted} throttled=${throttled} other=${other}"

	if [[ "${accepted}" -ne "${EXPECTED_ACCEPTED}" || "${throttled}" -ne "${EXPECTED_THROTTLED}" || "${other}" -ne 0 ]]; then
		fct_log "ERROR" "Capacity drill mismatch"
		for i in $(seq 1 "${BURST_COUNT}"); do
			printf '  request=%s status=%s body=%s\n' "${i}" "$(cat "${tmp}/${i}.status")" "$(cat "${tmp}/${i}.body")" >&2
		done
		exit 1
	fi

	if [[ "${POLL_GATES}" == "true" ]]; then
		for i in $(seq 1 "${BURST_COUNT}"); do
			if [[ "$(cat "${tmp}/${i}.status")" != "202" ]]; then
				continue
			fi
			local run_id
			run_id="$(jq -r '.run_id // empty' "${tmp}/${i}.body")"
			if [[ -n "${run_id}" ]]; then
				fct_wait_for_gate "${run_id}"
			fi
		done
	fi

	fct_log "INFO" "Capacity drill passed"
}


fct_main "$@"
