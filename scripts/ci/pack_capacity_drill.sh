#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"

API_URL="${BOTCHECK_API_URL:-http://localhost:7700}"
USER_TOKEN="${BOTCHECK_USER_TOKEN:-}"
PACK_ID="${BOTCHECK_PACK_ID:-}"
EXPECTED_MAX_RUNNING="${BOTCHECK_EXPECT_MAX_RUNNING:-5}"
EXPECTED_TOTAL_SCENARIOS="${BOTCHECK_PACK_EXPECT_TOTAL_SCENARIOS:-}"
EXPECTED_TERMINAL_STATES="${BOTCHECK_PACK_EXPECT_TERMINAL_STATES:-complete,partial,failed}"
EVIDENCE_DIR="${BOTCHECK_PACK_DRILL_EVIDENCE_DIR:-}"
POLL_TIMEOUT_S="${BOTCHECK_PACK_DRILL_TIMEOUT_S:-900}"
POLL_INTERVAL_S="${BOTCHECK_PACK_DRILL_POLL_S:-5}"

fct_usage() {
	cat <<EOF_USAGE
${SCRIPT_NAME}
Trigger a pack run and verify in-flight child run concurrency stays within the expected SIP slot ceiling.

Usage:
  ${SCRIPT_NAME} --pack-id <id> --user-token <token> [options]

Options:
  --api-url <url>              BotCheck API base URL (default: ${API_URL})
  --pack-id <id>               Pack ID to run
  --user-token <token>         User bearer token with pack run access
  --expect-max-running <n>     Maximum allowed concurrent child runs in running state (default: ${EXPECTED_MAX_RUNNING})
  --expect-total <n>           Optional expected total_scenarios for the pack run
  --expect-terminal <states>   Comma-separated allowed terminal states (default: ${EXPECTED_TERMINAL_STATES})
  --evidence-dir <path>        Optional output directory for drill artifacts (summary/detail/trace)
  --timeout-s <seconds>        Poll timeout before failing (default: ${POLL_TIMEOUT_S})
  --poll-s <seconds>           Poll interval in seconds (default: ${POLL_INTERVAL_S})
  -h, --help                   Show help and exit
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
		--pack-id)
			PACK_ID="${2:?--pack-id requires a value}"
			shift 2
			;;
		--user-token)
			USER_TOKEN="${2:?--user-token requires a value}"
			shift 2
			;;
		--expect-max-running)
			EXPECTED_MAX_RUNNING="${2:?--expect-max-running requires a value}"
			shift 2
			;;
		--expect-total)
			EXPECTED_TOTAL_SCENARIOS="${2:?--expect-total requires a value}"
			shift 2
			;;
		--expect-terminal)
			EXPECTED_TERMINAL_STATES="${2:?--expect-terminal requires a value}"
			shift 2
			;;
		--evidence-dir)
			EVIDENCE_DIR="${2:?--evidence-dir requires a value}"
			shift 2
			;;
		--timeout-s)
			POLL_TIMEOUT_S="${2:?--timeout-s requires a value}"
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

fct_trigger_pack_run() {
	local response body status
	response="$(curl -sS \
		-X POST \
		-H "Authorization: Bearer ${USER_TOKEN}" \
		"${API_URL%/}/packs/${PACK_ID}/run" \
		-w $'\n%{http_code}')"
	body="${response%$'\n'*}"
	status="${response##*$'\n'}"
	if [[ "${status}" != "202" ]]; then
		fct_log "ERROR" "Pack run trigger failed status=${status} body=${body}"
		exit 1
	fi
	printf '%s' "${body}" | jq -r '.pack_run_id // empty'
}

fct_http_get() {
	local path="${1}"
	curl -sS \
		-H "Authorization: Bearer ${USER_TOKEN}" \
		"${API_URL%/}${path}" \
		-w $'\n%{http_code}'
}

fct_state_allowed() {
	local state="${1}"
	local allowed_csv="${2}"
	local candidate value trimmed
	IFS=',' read -r -a candidate <<<"${allowed_csv}"
	for value in "${candidate[@]}"; do
		trimmed="${value#"${value%%[![:space:]]*}"}"
		trimmed="${trimmed%"${trimmed##*[![:space:]]}"}"
		if [[ "${state}" == "${trimmed}" ]]; then
			return 0
		fi
	done
	return 1
}

fct_main() {
	fct_parse_args "$@"
	fct_require_command "curl"
	fct_require_command "jq"

	[[ -n "${PACK_ID}" ]] || { fct_log "ERROR" "--pack-id is required"; exit 2; }
	[[ -n "${USER_TOKEN}" ]] || { fct_log "ERROR" "--user-token is required"; exit 2; }

	fct_log "INFO" "Triggering pack run for pack_id=${PACK_ID}"
	local pack_run_id
	pack_run_id="$(fct_trigger_pack_run)"
	if [[ -z "${pack_run_id}" ]]; then
		fct_log "ERROR" "Trigger response missing pack_run_id"
		exit 1
	fi
	fct_log "INFO" "Pack run started: ${pack_run_id}"

	local work_dir trace_path
	work_dir="$(mktemp -d)"
	trace_path="${work_dir}/poll_trace.tsv"
	trap 'rm -rf "${work_dir}"' EXIT

	local deadline peak_running
	deadline=$((SECONDS + POLL_TIMEOUT_S))
	peak_running=0

	local detail children
	local state completed total dispatched passed blocked failed inflight_count running_count
	state=""
	completed=0
	total=0
	dispatched=0
	passed=0
	blocked=0
	failed=0
	inflight_count=0
	running_count=0

	while ((SECONDS < deadline)); do
		local detail_response detail_status children_response children_status
		detail_response="$(fct_http_get "/pack-runs/${pack_run_id}")"
		detail="${detail_response%$'\n'*}"
		detail_status="${detail_response##*$'\n'}"
		if [[ "${detail_status}" != "200" ]]; then
			fct_log "ERROR" "Failed to fetch pack run detail status=${detail_status} body=${detail}"
			exit 1
		fi

		children_response="$(fct_http_get "/pack-runs/${pack_run_id}/runs?limit=1000")"
		children="${children_response%$'\n'*}"
		children_status="${children_response##*$'\n'}"
		if [[ "${children_status}" != "200" ]]; then
			fct_log "ERROR" "Failed to fetch pack run children status=${children_status} body=${children}"
			exit 1
		fi

		state="$(printf '%s' "${detail}" | jq -r '.state // empty')"
		completed="$(printf '%s' "${detail}" | jq -r '.completed // 0')"
		total="$(printf '%s' "${detail}" | jq -r '.total_scenarios // 0')"
		dispatched="$(printf '%s' "${detail}" | jq -r '.dispatched // 0')"
		passed="$(printf '%s' "${detail}" | jq -r '.passed // 0')"
		blocked="$(printf '%s' "${detail}" | jq -r '.blocked // 0')"
		failed="$(printf '%s' "${detail}" | jq -r '.failed // 0')"
		running_count="$(printf '%s' "${children}" | jq -r '[.items[] | select(((.run_state // .state // "") | ascii_downcase) == "running")] | length')"
		inflight_count="$(printf '%s' "${children}" | jq -r '[.items[] | select(((.run_state // .state // "") | ascii_downcase) | IN("pending","dispatched","running"))] | length')"

		if ((running_count > peak_running)); then
			peak_running="${running_count}"
		fi

		printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
			"$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
			"${state}" \
			"${running_count}" \
			"${inflight_count}" \
			"${completed}" \
			"${total}" \
			"${dispatched}" \
			"${blocked}" \
			"${failed}" >>"${trace_path}"

		fct_log "INFO" "state=${state} running=${running_count} inflight=${inflight_count} completed=${completed}/${total} peak=${peak_running}"

		if ((running_count > EXPECTED_MAX_RUNNING)); then
			fct_log "ERROR" "Running count exceeded expected max (${running_count} > ${EXPECTED_MAX_RUNNING})"
			exit 1
		fi

		if fct_state_allowed "${state}" "${EXPECTED_TERMINAL_STATES}"; then
			fct_log "INFO" "Pack run reached terminal state=${state}"
			break
		fi

		sleep "${POLL_INTERVAL_S}"
	done

	if ((SECONDS >= deadline)); then
		fct_log "ERROR" "Timed out waiting for terminal pack run state"
		exit 1
	fi

	if [[ -n "${EXPECTED_TOTAL_SCENARIOS}" && "${total}" -ne "${EXPECTED_TOTAL_SCENARIOS}" ]]; then
		fct_log "ERROR" "Unexpected pack size total_scenarios=${total} expected=${EXPECTED_TOTAL_SCENARIOS}"
		exit 1
	fi

	if [[ "${state}" != "cancelled" && "${completed}" -ne "${total}" ]]; then
		fct_log "ERROR" "Terminal pack run has incomplete counters completed=${completed} total=${total}"
		exit 1
	fi

	if [[ "${state}" != "cancelled" && "${inflight_count}" -ne 0 ]]; then
		fct_log "ERROR" "Terminal pack run still has in-flight children=${inflight_count}"
		exit 1
	fi

	if [[ -n "${EVIDENCE_DIR}" ]]; then
		mkdir -p "${EVIDENCE_DIR}"
		printf '%s' "${detail}" >"${EVIDENCE_DIR%/}/pack_capacity_detail_${pack_run_id}.json"
		printf '%s' "${children}" >"${EVIDENCE_DIR%/}/pack_capacity_children_${pack_run_id}.json"
		cp "${trace_path}" "${EVIDENCE_DIR%/}/pack_capacity_trace_${pack_run_id}.tsv"
		jq -n \
			--arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
			--arg api_url "${API_URL}" \
			--arg pack_id "${PACK_ID}" \
			--arg pack_run_id "${pack_run_id}" \
			--arg terminal_state "${state}" \
			--arg allowed_terminal_states "${EXPECTED_TERMINAL_STATES}" \
			--arg expected_total_scenarios "${EXPECTED_TOTAL_SCENARIOS}" \
			--argjson expected_max_running "${EXPECTED_MAX_RUNNING}" \
			--argjson peak_running "${peak_running}" \
			--argjson total_scenarios "${total}" \
			--argjson dispatched "${dispatched}" \
			--argjson completed "${completed}" \
			--argjson passed "${passed}" \
			--argjson blocked "${blocked}" \
			--argjson failed "${failed}" \
			'{
				generated_at: $generated_at,
				api_url: $api_url,
				pack_id: $pack_id,
				pack_run_id: $pack_run_id,
				terminal_state: $terminal_state,
				allowed_terminal_states: $allowed_terminal_states,
				expected_total_scenarios: ($expected_total_scenarios | if . == "" then null else (tonumber) end),
				expected_max_running: $expected_max_running,
				peak_running: $peak_running,
				total_scenarios: $total_scenarios,
				dispatched: $dispatched,
				completed: $completed,
				passed: $passed,
				blocked: $blocked,
				failed: $failed
			}' >"${EVIDENCE_DIR%/}/pack_capacity_summary_${pack_run_id}.json"
		fct_log "INFO" "Evidence written to ${EVIDENCE_DIR%/}"
	fi

	fct_log "INFO" "Pack capacity drill passed (peak_running=${peak_running}, expected_max=${EXPECTED_MAX_RUNNING})"
}

fct_main "$@"
