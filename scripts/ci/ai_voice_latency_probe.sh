#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"

API_URL="${BOTCHECK_API_URL:-http://localhost:7700}"
AGENT_METRICS_URL="${BOTCHECK_AGENT_METRICS_URL:-http://localhost:9102/metrics}"
AI_SCENARIO_ID="${BOTCHECK_AI_SCENARIO_ID:-}"
TRANSPORT_PROFILE_ID="${BOTCHECK_TRANSPORT_PROFILE_ID:-}"
USER_TOKEN="${BOTCHECK_USER_TOKEN:-}"
SAMPLES="${BOTCHECK_AI_VOICE_LATENCY_SAMPLES:-3}"
POLL_INTERVAL_S="${BOTCHECK_AI_VOICE_LATENCY_POLL_INTERVAL_S:-2}"
RUN_TIMEOUT_S="${BOTCHECK_AI_VOICE_LATENCY_RUN_TIMEOUT_S:-180}"
MODE_LABEL="${BOTCHECK_AI_VOICE_MODE_LABEL:-shared_path}"
RETENTION_PROFILE="${BOTCHECK_AI_VOICE_RETENTION_PROFILE:-standard}"
EVIDENCE_DIR="${BOTCHECK_AI_VOICE_EVIDENCE_DIR:-}"

fct_usage() {
	cat <<EOF_USAGE
${SCRIPT_NAME}
Trigger AI voice runs, wait for terminal state, and summarize Phase 40 latency
metrics from the harness agent.

Usage:
  ${SCRIPT_NAME} --ai-scenario-id <id> --user-token <token> [options]

Options:
  --api-url <url>               BotCheck API base URL (default: ${API_URL})
  --agent-metrics-url <url>     Harness agent metrics URL (default: ${AGENT_METRICS_URL})
  --ai-scenario-id <id>         AI scenario ID to benchmark
  --transport-profile-id <id>   Optional voice transport profile / destination
  --user-token <token>          User bearer token
  --samples <n>                 Number of runs to execute (default: ${SAMPLES})
  --poll-interval <seconds>     Poll interval while waiting for run completion (default: ${POLL_INTERVAL_S})
  --run-timeout <seconds>       Per-run timeout while waiting for terminal state (default: ${RUN_TIMEOUT_S})
  --mode-label <label>          Evidence label for this benchmark lane (default: ${MODE_LABEL})
  --retention-profile <name>    Retention profile override (default: ${RETENTION_PROFILE})
  --evidence-dir <path>         Optional directory to write metrics snapshots and summary
  -h, --help                    Show help and exit
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
		--agent-metrics-url)
			AGENT_METRICS_URL="${2:?--agent-metrics-url requires a value}"
			shift 2
			;;
		--ai-scenario-id)
			AI_SCENARIO_ID="${2:?--ai-scenario-id requires a value}"
			shift 2
			;;
		--transport-profile-id)
			TRANSPORT_PROFILE_ID="${2:?--transport-profile-id requires a value}"
			shift 2
			;;
		--user-token)
			USER_TOKEN="${2:?--user-token requires a value}"
			shift 2
			;;
		--samples)
			SAMPLES="${2:?--samples requires a value}"
			shift 2
			;;
		--poll-interval)
			POLL_INTERVAL_S="${2:?--poll-interval requires a value}"
			shift 2
			;;
		--run-timeout)
			RUN_TIMEOUT_S="${2:?--run-timeout requires a value}"
			shift 2
			;;
		--mode-label)
			MODE_LABEL="${2:?--mode-label requires a value}"
			shift 2
			;;
		--retention-profile)
			RETENTION_PROFILE="${2:?--retention-profile requires a value}"
			shift 2
			;;
		--evidence-dir)
			EVIDENCE_DIR="${2:?--evidence-dir requires a value}"
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

fct_fetch_metrics() {
	local output_path="${1}"
	curl -fsS "${AGENT_METRICS_URL}" >"${output_path}"
}

fct_metric_total() {
	local metrics_path="${1}"
	local metric_name="${2}"
	local label_filter="${3:-}"
	awk -v metric="${metric_name}" -v label_filter="${label_filter}" '
		function matches_all_filters(key, filter_string,    n, i, filters) {
			if (filter_string == "") {
				return 1
			}
			n = split(filter_string, filters, " ")
			for (i = 1; i <= n; i += 1) {
				if (filters[i] != "" && index(key, filters[i]) == 0) {
					return 0
				}
			}
			return 1
		}
		{
			key = $1
			value = $2
			if (key == metric || index(key, metric "{") == 1) {
				if (matches_all_filters(key, label_filter)) {
					sum += value + 0
				}
			}
		}
		END {
			printf "%.6f", sum + 0
		}
	' "${metrics_path}"
}

fct_metric_delta() {
	local before_path="${1}"
	local after_path="${2}"
	local metric_name="${3}"
	local label_filter="${4:-}"
	local before_value after_value
	before_value="$(fct_metric_total "${before_path}" "${metric_name}" "${label_filter}")"
	after_value="$(fct_metric_total "${after_path}" "${metric_name}" "${label_filter}")"
	awk -v before="${before_value}" -v after="${after_value}" 'BEGIN { printf "%.6f", after - before }'
}

fct_histogram_avg_ms_delta() {
	local before_path="${1}"
	local after_path="${2}"
	local metric_prefix="${3}"
	local label_filter="${4:-}"
	local delta_sum delta_count
	delta_sum="$(fct_metric_delta "${before_path}" "${after_path}" "${metric_prefix}_sum" "${label_filter}")"
	delta_count="$(fct_metric_delta "${before_path}" "${after_path}" "${metric_prefix}_count" "${label_filter}")"
	awk -v delta_sum="${delta_sum}" -v delta_count="${delta_count}" '
		BEGIN {
			if (delta_count <= 0) {
				printf "0.000"
			} else {
				printf "%.3f", (delta_sum / delta_count) * 1000
			}
		}
	'
}

fct_create_run() {
	local response body status
	response="$(
		jq -cn \
			--arg ai_scenario_id "${AI_SCENARIO_ID}" \
			--arg transport_profile_id "${TRANSPORT_PROFILE_ID}" \
			--arg retention_profile "${RETENTION_PROFILE}" '
				{
					ai_scenario_id: $ai_scenario_id,
					retention_profile: $retention_profile
				}
				+ (if $transport_profile_id == "" then {} else {transport_profile_id: $transport_profile_id} end)
			' \
		| curl -sS \
			-X POST \
			-H "Authorization: Bearer ${USER_TOKEN}" \
			-H "Content-Type: application/json" \
			--data-binary @- \
			"${API_URL%/}/runs/" \
			-w $'\n%{http_code}'
	)"
	body="$(printf '%s' "${response}" | sed '$d')"
	status="$(printf '%s' "${response}" | tail -n1)"
	if [[ "${status}" != "202" ]]; then
		fct_log "ERROR" "Run create failed status=${status} body=${body}"
		exit 1
	fi
	printf '%s' "${body}" | jq -r '.run_id'
}

fct_wait_for_terminal_run() {
	local run_id="${1}"
	local started_monotonic state detail raw
	started_monotonic="$(date +%s)"
	while true; do
		raw="$(curl -fsS -H "Authorization: Bearer ${USER_TOKEN}" "${API_URL%/}/runs/${run_id}")"
		state="$(printf '%s' "${raw}" | jq -r '.state')"
		case "${state}" in
		complete | failed | error)
			printf '%s' "${raw}"
			return
			;;
		esac
		if (( "$(date +%s)" - started_monotonic >= RUN_TIMEOUT_S )); then
			fct_log "ERROR" "Run ${run_id} did not reach terminal state within ${RUN_TIMEOUT_S}s (last_state=${state})"
			exit 1
		fi
		sleep "${POLL_INTERVAL_S}"
	done
}

fct_write_summary() {
	local before_path="${1}"
	local after_path="${2}"
	local samples_path="${3}"
	local summary_path="${4}"

	local ai_filter preview_filter reply_filter decision_filter llm_gap_filter playback_filter
	ai_filter='scenario_kind="ai"'
	reply_filter='scenario_kind="ai"'
	decision_filter='scenario_kind="ai"'
	llm_gap_filter='scenario_kind="ai"'
	playback_filter='scenario_kind="ai"'
	preview_filter='scenario_kind="ai"'

	local reply_count_delta decision_count_delta llm_gap_count_delta playback_count_delta
	reply_count_delta="$(fct_metric_delta "${before_path}" "${after_path}" "botcheck_ai_caller_reply_latency_seconds_count" "${reply_filter}")"
	decision_count_delta="$(fct_metric_delta "${before_path}" "${after_path}" "botcheck_ai_caller_decision_latency_seconds_count" "${decision_filter}")"
	llm_gap_count_delta="$(fct_metric_delta "${before_path}" "${after_path}" "botcheck_ai_caller_llm_request_start_gap_seconds_count" "${llm_gap_filter}")"
	playback_count_delta="$(fct_metric_delta "${before_path}" "${after_path}" "botcheck_ai_caller_decision_to_playback_start_gap_seconds_count" "${playback_filter}")"

	local preview_events_delta spec_started_delta spec_committed_delta spec_discarded_delta spec_cancelled_delta spec_error_delta
	local fast_ack_dataset_delta fast_ack_heuristic_delta
	local early_started_delta early_committed_delta early_stale_delta early_cancelled_delta early_error_delta

	preview_events_delta="$(fct_metric_delta "${before_path}" "${after_path}" "botcheck_ai_voice_preview_events_total" "${preview_filter}")"
	spec_started_delta="$(fct_metric_delta "${before_path}" "${after_path}" "botcheck_ai_voice_speculative_plans_total" 'outcome="started" scenario_kind="ai"')"
	spec_committed_delta="$(fct_metric_delta "${before_path}" "${after_path}" "botcheck_ai_voice_speculative_plans_total" 'outcome="committed" scenario_kind="ai"')"
	spec_discarded_delta="$(fct_metric_delta "${before_path}" "${after_path}" "botcheck_ai_voice_speculative_plans_total" 'outcome="discarded" scenario_kind="ai"')"
	spec_cancelled_delta="$(fct_metric_delta "${before_path}" "${after_path}" "botcheck_ai_voice_speculative_plans_total" 'outcome="cancelled" scenario_kind="ai"')"
	spec_error_delta="$(fct_metric_delta "${before_path}" "${after_path}" "botcheck_ai_voice_speculative_plans_total" 'outcome="error" scenario_kind="ai"')"
	fast_ack_dataset_delta="$(fct_metric_delta "${before_path}" "${after_path}" "botcheck_ai_voice_fast_ack_total" 'source="dataset_input" scenario_kind="ai"')"
	fast_ack_heuristic_delta="$(fct_metric_delta "${before_path}" "${after_path}" "botcheck_ai_voice_fast_ack_total" 'source="heuristic" scenario_kind="ai"')"
	early_started_delta="$(fct_metric_delta "${before_path}" "${after_path}" "botcheck_ai_voice_early_playback_total" 'outcome="started" scenario_kind="ai"')"
	early_committed_delta="$(fct_metric_delta "${before_path}" "${after_path}" "botcheck_ai_voice_early_playback_total" 'outcome="committed" scenario_kind="ai"')"
	early_stale_delta="$(fct_metric_delta "${before_path}" "${after_path}" "botcheck_ai_voice_early_playback_total" 'outcome="stale_suppressed" scenario_kind="ai"')"
	early_cancelled_delta="$(fct_metric_delta "${before_path}" "${after_path}" "botcheck_ai_voice_early_playback_total" 'outcome="cancelled" scenario_kind="ai"')"
	early_error_delta="$(fct_metric_delta "${before_path}" "${after_path}" "botcheck_ai_voice_early_playback_total" 'outcome="error" scenario_kind="ai"')"

	jq -n \
		--arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
		--arg api_url "${API_URL}" \
		--arg agent_metrics_url "${AGENT_METRICS_URL}" \
		--arg ai_scenario_id "${AI_SCENARIO_ID}" \
		--arg transport_profile_id "${TRANSPORT_PROFILE_ID}" \
		--arg mode_label "${MODE_LABEL}" \
		--argjson samples "${SAMPLES}" \
		--argjson run_timeout_s "${RUN_TIMEOUT_S}" \
		--argjson poll_interval_s "${POLL_INTERVAL_S}" \
		--slurpfile sample_rows "${samples_path}" \
		--argjson reply_count_delta "${reply_count_delta}" \
		--argjson reply_avg_ms "$(fct_histogram_avg_ms_delta "${before_path}" "${after_path}" "botcheck_ai_caller_reply_latency_seconds" "${reply_filter}")" \
		--argjson decision_count_delta "${decision_count_delta}" \
		--argjson decision_avg_ms "$(fct_histogram_avg_ms_delta "${before_path}" "${after_path}" "botcheck_ai_caller_decision_latency_seconds" "${decision_filter}")" \
		--argjson llm_gap_count_delta "${llm_gap_count_delta}" \
		--argjson llm_gap_avg_ms "$(fct_histogram_avg_ms_delta "${before_path}" "${after_path}" "botcheck_ai_caller_llm_request_start_gap_seconds" "${llm_gap_filter}")" \
		--argjson playback_count_delta "${playback_count_delta}" \
		--argjson playback_avg_ms "$(fct_histogram_avg_ms_delta "${before_path}" "${after_path}" "botcheck_ai_caller_decision_to_playback_start_gap_seconds" "${playback_filter}")" \
		--argjson preview_events_delta "${preview_events_delta}" \
		--argjson spec_started_delta "${spec_started_delta}" \
		--argjson spec_committed_delta "${spec_committed_delta}" \
		--argjson spec_discarded_delta "${spec_discarded_delta}" \
		--argjson spec_cancelled_delta "${spec_cancelled_delta}" \
		--argjson spec_error_delta "${spec_error_delta}" \
		--argjson fast_ack_dataset_delta "${fast_ack_dataset_delta}" \
		--argjson fast_ack_heuristic_delta "${fast_ack_heuristic_delta}" \
		--argjson early_started_delta "${early_started_delta}" \
		--argjson early_committed_delta "${early_committed_delta}" \
		--argjson early_stale_delta "${early_stale_delta}" \
		--argjson early_cancelled_delta "${early_cancelled_delta}" \
		--argjson early_error_delta "${early_error_delta}" '
		{
			generated_at: $generated_at,
			api_url: $api_url,
			agent_metrics_url: $agent_metrics_url,
			ai_scenario_id: $ai_scenario_id,
			transport_profile_id: ($transport_profile_id | select(. != "")),
			mode_label: $mode_label,
			samples: $samples,
			run_timeout_s: $run_timeout_s,
			poll_interval_s: $poll_interval_s,
			note: "Agent metrics are process-wide. Run the probe in a quiet environment for clean deltas.",
			runs: ($sample_rows[0]),
			metrics: {
				reply_latency: {
					count_delta: $reply_count_delta,
					avg_ms: $reply_avg_ms
				},
				decision_latency: {
					count_delta: $decision_count_delta,
					avg_ms: $decision_avg_ms
				},
				llm_request_start_gap: {
					count_delta: $llm_gap_count_delta,
					avg_ms: $llm_gap_avg_ms
				},
				decision_to_playback_start_gap: {
					count_delta: $playback_count_delta,
					avg_ms: $playback_avg_ms
				},
				preview_events_total_delta: $preview_events_delta,
				speculative_plans: {
					started: $spec_started_delta,
					committed: $spec_committed_delta,
					discarded: $spec_discarded_delta,
					cancelled: $spec_cancelled_delta,
					error: $spec_error_delta
				},
				fast_ack: {
					dataset_input: $fast_ack_dataset_delta,
					heuristic: $fast_ack_heuristic_delta
				},
				early_playback: {
					started: $early_started_delta,
					committed: $early_committed_delta,
					stale_suppressed: $early_stale_delta,
					cancelled: $early_cancelled_delta,
					error: $early_error_delta
				}
			}
		}
	' >"${summary_path}"
}

fct_main() {
	fct_parse_args "$@"
	fct_require_command "curl"
	fct_require_command "jq"
	fct_require_command "awk"

	[[ -n "${AI_SCENARIO_ID}" ]] || { fct_log "ERROR" "--ai-scenario-id is required"; exit 2; }
	[[ -n "${USER_TOKEN}" ]] || { fct_log "ERROR" "--user-token is required"; exit 2; }
	[[ "${SAMPLES}" =~ ^[0-9]+$ ]] || { fct_log "ERROR" "--samples must be a positive integer"; exit 2; }
	[[ "${SAMPLES}" -ge 1 ]] || { fct_log "ERROR" "--samples must be >= 1"; exit 2; }
	[[ "${RUN_TIMEOUT_S}" =~ ^[0-9]+$ ]] || { fct_log "ERROR" "--run-timeout must be a positive integer"; exit 2; }
	[[ "${RUN_TIMEOUT_S}" -ge 1 ]] || { fct_log "ERROR" "--run-timeout must be >= 1"; exit 2; }

	local work_dir before_metrics after_metrics runs_jsonl summary_path
	work_dir="$(mktemp -d)"
	before_metrics="${work_dir}/agent_metrics_before.prom"
	after_metrics="${work_dir}/agent_metrics_after.prom"
	runs_jsonl="${work_dir}/runs.jsonl"
	summary_path="${work_dir}/ai_voice_latency_summary.json"
	trap 'rm -rf "${work_dir}"' EXIT

	fct_fetch_metrics "${before_metrics}"

	local i
	for i in $(seq 1 "${SAMPLES}"); do
		local run_id run_detail state
		run_id="$(fct_create_run)"
		fct_log "INFO" "sample=${i}/${SAMPLES} run_id=${run_id} created"
		run_detail="$(fct_wait_for_terminal_run "${run_id}")"
		state="$(printf '%s' "${run_detail}" | jq -r '.state')"
		fct_log "INFO" "sample=${i}/${SAMPLES} run_id=${run_id} state=${state}"
		printf '%s\n' "${run_detail}" >>"${runs_jsonl}"
	done

	fct_fetch_metrics "${after_metrics}"
	fct_write_summary "${before_metrics}" "${after_metrics}" "${runs_jsonl}" "${summary_path}"

	if [[ -n "${EVIDENCE_DIR}" ]]; then
		mkdir -p "${EVIDENCE_DIR}"
		cp "${before_metrics}" "${EVIDENCE_DIR%/}/agent_metrics_before.prom"
		cp "${after_metrics}" "${EVIDENCE_DIR%/}/agent_metrics_after.prom"
		cp "${runs_jsonl}" "${EVIDENCE_DIR%/}/run_details.jsonl"
		cp "${summary_path}" "${EVIDENCE_DIR%/}/ai_voice_latency_summary.json"
		fct_log "INFO" "Evidence written to ${EVIDENCE_DIR%/}"
	fi

	cat "${summary_path}"
}

fct_main "$@"
