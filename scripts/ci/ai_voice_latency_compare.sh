#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"

OUTPUT_PATH="${BOTCHECK_AI_VOICE_COMPARE_OUTPUT:-}"
JSON_OUTPUT_PATH="${BOTCHECK_AI_VOICE_COMPARE_JSON_OUTPUT:-}"

declare -a BUNDLES=()

fct_usage() {
	cat <<EOF_USAGE
${SCRIPT_NAME}
Compare Phase 40 AI voice latency evidence bundles and emit a markdown decision
matrix plus an optional machine-readable summary.

Usage:
  ${SCRIPT_NAME} --bundle <evidence_dir> --bundle <evidence_dir> [options]

Options:
  --bundle <path>        Evidence directory containing ai_voice_latency_summary.json
                         Repeat for each lane; requires at least two bundles.
  --output <path>        Optional markdown output path
  --json-output <path>   Optional JSON output path
  -h, --help             Show help and exit
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
		--bundle)
			BUNDLES+=("${2:?--bundle requires a value}")
			shift 2
			;;
		--output)
			OUTPUT_PATH="${2:?--output requires a value}"
			shift 2
			;;
		--json-output)
			JSON_OUTPUT_PATH="${2:?--json-output requires a value}"
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

fct_require_bundle() {
	local bundle_path="${1}"
	local summary_path="${bundle_path%/}/ai_voice_latency_summary.json"
	if [[ ! -d "${bundle_path}" ]]; then
		fct_log "ERROR" "Bundle directory not found: ${bundle_path}"
		exit 1
	fi
	if [[ ! -f "${summary_path}" ]]; then
		fct_log "ERROR" "Missing summary file: ${summary_path}"
		exit 1
	fi
	if ! jq empty "${summary_path}" 2>/dev/null; then
		fct_log "ERROR" "Malformed JSON in ${summary_path}"
		exit 1
	fi
}

fct_lane_debugging_quality() {
	local mode_label="${1}"
	case "${mode_label}" in
	shared_path)
		printf 'High'
		;;
	overlap_enabled)
		printf 'Medium'
		;;
	native_speech)
		printf 'Variable'
		;;
	*)
		printf 'Unknown'
		;;
	esac
}

fct_lane_provider_flexibility() {
	local mode_label="${1}"
	case "${mode_label}" in
	shared_path | overlap_enabled)
		printf 'High'
		;;
	native_speech)
		printf 'Medium'
		;;
	*)
		printf 'Unknown'
		;;
	esac
}

fct_lane_operational_complexity() {
	local mode_label="${1}"
	case "${mode_label}" in
	shared_path)
		printf 'Medium'
		;;
	overlap_enabled)
		printf 'High'
		;;
	native_speech)
		printf 'Medium'
		;;
	*)
		printf 'Unknown'
		;;
	esac
}

fct_fidelity_signal() {
	local error_runs="${1}"
	local stale_suppressed="${2}"
	local cancelled="${3}"
	if awk -v errors="${error_runs}" -v stale="${stale_suppressed}" 'BEGIN { exit !(errors <= 0 && stale <= 0) }'; then
		printf 'Strong'
		return
	fi
	if awk -v errors="${error_runs}" -v stale="${stale_suppressed}" -v cancelled="${cancelled}" \
		'BEGIN { exit !(errors <= 0 && stale <= 1 && cancelled <= 1) }'; then
		printf 'Watch'
		return
	fi
	printf 'Risk'
}

fct_numeric_min_label() {
	local rows_path="${1}"
	local field_name="${2}"
	jq -r --arg field "${field_name}" '
		map(select(.[$field] != null))
		| min_by(.[$field] + 0)
		| .mode_label // "N/A"
	' "${rows_path}"
}

fct_numeric_max_label() {
	local rows_path="${1}"
	local field_name="${2}"
	jq -r --arg field "${field_name}" '
		map(select(.[$field] != null))
		| max_by(.[$field] + 0)
		| .mode_label // "N/A"
	' "${rows_path}"
}

fct_build_rows_json() {
	local rows_path="${1}"
	local first=1
	printf '[' >"${rows_path}"
	local bundle_path
	for bundle_path in "${BUNDLES[@]}"; do
		local summary_path mode_label error_runs early_stale early_cancelled
		summary_path="${bundle_path%/}/ai_voice_latency_summary.json"

		# Extract the three fields needed by shell helper functions; use // 0
		# defaults so null JSON values become numeric 0 rather than the string
		# "null", which would cause awk to silently coerce them to zero and
		# misclassify fidelity for bundles with sparse metric coverage.
		mode_label="$(jq -r '.mode_label // "unknown"' "${summary_path}")"
		error_runs="$(jq -r '[(.runs // [])[] | select(.state == "error")] | length' "${summary_path}")"
		early_stale="$(jq -r '.metrics.early_playback.stale_suppressed // 0' "${summary_path}")"
		early_cancelled="$(jq -r '.metrics.early_playback.cancelled // 0' "${summary_path}")"

		if [[ "${first}" -eq 0 ]]; then
			printf ',' >>"${rows_path}"
		fi
		first=0

		# Build the entire row object with a single jq invocation using
		# --slurpfile. All numeric fields are extracted inside jq with // 0 or
		# // null defaults, so missing or null-typed fields never trigger an
		# --argjson parse error and never produce invalid JSON.
		jq -n \
			--slurpfile summary "${summary_path}" \
			--arg bundle_path "${bundle_path}" \
			--arg mode_label "${mode_label}" \
			--arg debugging_quality "$(fct_lane_debugging_quality "${mode_label}")" \
			--arg provider_flexibility "$(fct_lane_provider_flexibility "${mode_label}")" \
			--arg operational_complexity "$(fct_lane_operational_complexity "${mode_label}")" \
			--arg transcript_fidelity "$(fct_fidelity_signal "${error_runs}" "${early_stale}" "${early_cancelled}")" \
			'($summary[0]) as $s |
			{
				bundle_path: $bundle_path,
				mode_label: $mode_label,
				samples: ($s.samples // 0),
				reply_avg_ms: ($s.metrics.reply_latency.avg_ms),
				decision_avg_ms: ($s.metrics.decision_latency.avg_ms),
				llm_gap_avg_ms: ($s.metrics.llm_request_start_gap.avg_ms),
				playback_avg_ms: ($s.metrics.decision_to_playback_start_gap.avg_ms),
				preview_events_total_delta: ($s.metrics.preview_events_total_delta // 0),
				spec_started: ($s.metrics.speculative_plans.started // 0),
				spec_committed: ($s.metrics.speculative_plans.committed // 0),
				spec_discarded: ($s.metrics.speculative_plans.discarded // 0),
				spec_cancelled: ($s.metrics.speculative_plans.cancelled // 0),
				spec_error: ($s.metrics.speculative_plans.error // 0),
				fast_ack_dataset: ($s.metrics.fast_ack.dataset_input // 0),
				fast_ack_heuristic: ($s.metrics.fast_ack.heuristic // 0),
				early_started: ($s.metrics.early_playback.started // 0),
				early_committed: ($s.metrics.early_playback.committed // 0),
				early_stale_suppressed: ($s.metrics.early_playback.stale_suppressed // 0),
				early_cancelled: ($s.metrics.early_playback.cancelled // 0),
				early_error: ($s.metrics.early_playback.error // 0),
				complete_runs: ([($s.runs // [])[] | select(.state == "complete")] | length),
				failed_runs: ([($s.runs // [])[] | select(.state == "failed")] | length),
				error_runs: ([($s.runs // [])[] | select(.state == "error")] | length),
				transcript_fidelity: $transcript_fidelity,
				debugging_quality: $debugging_quality,
				provider_flexibility: $provider_flexibility,
				operational_complexity: $operational_complexity
			}' >>"${rows_path}"
	done
	printf ']\n' >>"${rows_path}"
}

fct_write_markdown() {
	local rows_path="${1}"
	local markdown_path="${2}"
	local fastest_lane lowest_playback_lane most_stable_lane
	fastest_lane="$(fct_numeric_min_label "${rows_path}" "reply_avg_ms")"
	lowest_playback_lane="$(fct_numeric_min_label "${rows_path}" "playback_avg_ms")"
	most_stable_lane="$(fct_numeric_min_label "${rows_path}" "early_stale_suppressed")"

	{
		printf '# Phase 40 AI Voice Benchmark Decision Matrix\n\n'
		printf 'Generated by `%s` on %s.\n\n' "${SCRIPT_NAME}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
		printf '## Lane Summary\n\n'
		printf '| Lane | Samples | Reply avg ms | Decision avg ms | LLM gap avg ms | Playback gap avg ms | Fast-ack total | Early committed | Early stale | Run errors |\n'
		printf '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n'
		jq -r '
			.[] |
			"| \(.mode_label) | \(.samples) | \(.reply_avg_ms) | \(.decision_avg_ms) | \(.llm_gap_avg_ms) | \(.playback_avg_ms) | \((.fast_ack_dataset + .fast_ack_heuristic)) | \(.early_committed) | \(.early_stale_suppressed) | \(.error_runs) |"
		' "${rows_path}"
		printf '\n## Decision Matrix\n\n'
		printf '| Lane | Latency | Transcript fidelity | Debugging quality | Provider flexibility | Operational complexity |\n'
		printf '| --- | --- | --- | --- | --- | --- |\n'
		jq -r '
			.[] |
			"| \(.mode_label) | reply \(.reply_avg_ms) ms / playback \(.playback_avg_ms) ms | \(.transcript_fidelity) | \(.debugging_quality) | \(.provider_flexibility) | \(.operational_complexity) |"
		' "${rows_path}"
		printf '\n## Recommendation\n\n'
		printf -- '- Fastest lane by reply latency: `%s`\n' "${fastest_lane}"
		printf -- '- Lowest decision-to-playback gap: `%s`\n' "${lowest_playback_lane}"
		printf -- '- Lowest stale-suppression pressure: `%s`\n' "${most_stable_lane}"
		printf '\n## Notes\n\n'
		printf -- '- `transcript_fidelity` is a benchmark proxy derived from run `error` counts plus early-playback stale/cancel counters. It is not a semantic transcript-quality score.\n'
		printf -- '- `debugging_quality`, `provider_flexibility`, and `operational_complexity` are lane-level operational assessments derived from the runtime mode, not raw Prometheus metrics.\n'
		printf -- '- Compare this matrix alongside the per-lane `ai_voice_latency_summary.json` bundles before choosing a default runtime path.\n'
	} >"${markdown_path}"
}

fct_main() {
	fct_parse_args "$@"
	fct_require_command "jq"

	if [[ "${#BUNDLES[@]}" -lt 2 ]]; then
		fct_log "ERROR" "Provide at least two --bundle paths to compare"
		exit 2
	fi

	local bundle_path
	for bundle_path in "${BUNDLES[@]}"; do
		fct_require_bundle "${bundle_path}"
	done

	local work_dir rows_path markdown_path json_path
	work_dir="$(mktemp -d)"
	rows_path="${work_dir}/rows.json"
	markdown_path="${work_dir}/phase40_ai_voice_decision_matrix.md"
	json_path="${work_dir}/phase40_ai_voice_decision_matrix.json"
	trap 'rm -rf "${work_dir:-}"' EXIT

	fct_build_rows_json "${rows_path}"
	fct_write_markdown "${rows_path}" "${markdown_path}"
	cp "${rows_path}" "${json_path}"

	if [[ -n "${OUTPUT_PATH}" ]]; then
		mkdir -p "$(dirname "${OUTPUT_PATH}")"
		cp "${markdown_path}" "${OUTPUT_PATH}"
		fct_log "INFO" "Markdown decision matrix written to ${OUTPUT_PATH}"
	fi
	if [[ -n "${JSON_OUTPUT_PATH}" ]]; then
		mkdir -p "$(dirname "${JSON_OUTPUT_PATH}")"
		cp "${json_path}" "${JSON_OUTPUT_PATH}"
		fct_log "INFO" "JSON comparison written to ${JSON_OUTPUT_PATH}"
	fi

	cat "${markdown_path}"
}

fct_main "$@"
