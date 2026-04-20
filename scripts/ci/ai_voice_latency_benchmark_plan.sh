#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"

DATE_LABEL="${BOTCHECK_AI_VOICE_DATE_LABEL:-$(date +%Y%m%d)}"
EVIDENCE_ROOT="${BOTCHECK_AI_VOICE_EVIDENCE_ROOT:-docs/evidence/phase40}"
AI_SCENARIO_ID="${BOTCHECK_AI_SCENARIO_ID:-}"
TRANSPORT_PROFILE_ID="${BOTCHECK_TRANSPORT_PROFILE_ID:-}"
USER_TOKEN="${BOTCHECK_USER_TOKEN:-}"
INCLUDE_NATIVE_SPEECH="${BOTCHECK_AI_VOICE_INCLUDE_NATIVE_SPEECH:-1}"
OUTPUT_PATH="${BOTCHECK_AI_VOICE_PLAN_OUTPUT:-}"

fct_usage() {
	cat <<EOF_USAGE
${SCRIPT_NAME}
Generate a Phase 40 live-benchmark execution plan covering shared-path,
overlap-enabled, and optional native-speech lanes.

Usage:
  ${SCRIPT_NAME} --ai-scenario-id <id> [options]

Options:
  --ai-scenario-id <id>         AI scenario ID to benchmark
  --transport-profile-id <id>   Optional voice destination / transport profile
  --user-token <token>          Optional token to inline into generated commands
  --date-label <label>          Evidence label prefix (default: ${DATE_LABEL})
  --evidence-root <path>        Evidence root (default: ${EVIDENCE_ROOT})
  --include-native-speech <0|1> Include Phase 39 native speech lane (default: ${INCLUDE_NATIVE_SPEECH})
  --output <path>               Optional markdown output path
  -h, --help                    Show help and exit
EOF_USAGE
}

fct_log() {
	local level="${1}"
	shift
	printf '%s [%s] %s\n' "${level}" "${SCRIPT_NAME}" "$*" >&2
}

fct_parse_args() {
	while [[ $# -gt 0 ]]; do
		case "$1" in
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
		--date-label)
			DATE_LABEL="${2:?--date-label requires a value}"
			shift 2
			;;
		--evidence-root)
			EVIDENCE_ROOT="${2:?--evidence-root requires a value}"
			shift 2
			;;
		--include-native-speech)
			INCLUDE_NATIVE_SPEECH="${2:?--include-native-speech requires 0|1}"
			shift 2
			;;
		--output)
			OUTPUT_PATH="${2:?--output requires a value}"
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

fct_print_env_line() {
	local key="${1}"
	local value="${2}"
	if [[ -n "${value}" ]]; then
		printf '%s=%q \\\n' "${key}" "${value}"
	fi
}

fct_render_probe_block() {
	local mode_label="${1}"
	local lane_suffix="${2}"
	local lane_dir="${EVIDENCE_ROOT%/}/${DATE_LABEL}-${lane_suffix}"

	printf '```bash\n'
	fct_print_env_line "BOTCHECK_AI_SCENARIO_ID" "${AI_SCENARIO_ID}"
	fct_print_env_line "BOTCHECK_TRANSPORT_PROFILE_ID" "${TRANSPORT_PROFILE_ID}"
	fct_print_env_line "BOTCHECK_USER_TOKEN" "${USER_TOKEN}"
	printf 'BOTCHECK_AI_VOICE_MODE_LABEL=%q \\\n' "${mode_label}"
	printf 'BOTCHECK_AI_VOICE_EVIDENCE_DIR=%q \\\n' "${lane_dir}"
	printf 'make test-ai-voice-latency\n'
	printf '```\n'
}

fct_render_native_note() {
	cat <<'EOF_NATIVE'
Native speech prerequisites:

- Phase 39 native speech runtime is enabled on the target harness worker
- the selected AI scenario is configured for the `speech` runtime lane
- the selected tenant has a compatible speech provider assigned

EOF_NATIVE
}

fct_main() {
	fct_parse_args "$@"

	[[ -n "${AI_SCENARIO_ID}" ]] || { fct_log "ERROR" "--ai-scenario-id is required"; exit 2; }
	[[ "${INCLUDE_NATIVE_SPEECH}" =~ ^[01]$ ]] || { fct_log "ERROR" "--include-native-speech must be 0 or 1"; exit 2; }

	local tmp_path
	tmp_path="$(mktemp)"
	trap 'rm -f "${tmp_path:-}"' EXIT

	{
		printf '# Phase 40 Live Benchmark Plan\n\n'
		printf 'Date label: `%s`\n\n' "${DATE_LABEL}"
		printf 'AI scenario: `%s`\n\n' "${AI_SCENARIO_ID}"
		if [[ -n "${TRANSPORT_PROFILE_ID}" ]]; then
			printf 'Transport profile: `%s`\n\n' "${TRANSPORT_PROFILE_ID}"
		fi
		printf 'Evidence root: `%s`\n\n' "${EVIDENCE_ROOT}"
		printf '## Lane 1: Shared Path\n\n'
		printf 'Run this with overlap flags disabled.\n\n'
		fct_render_probe_block "shared_path" "shared-path"
		printf '\n## Lane 2: Overlap Enabled\n\n'
		printf 'Run this with the Phase 40 overlap flags enabled on the harness worker:\n\n'
		printf -- '- `ai_voice_preview_events_enabled=true`\n'
		printf -- '- `ai_voice_speculative_planning_enabled=true`\n'
		printf -- '- `ai_voice_fast_ack_enabled=true`\n'
		printf -- '- `ai_voice_early_playback_enabled=true`\n\n'
		fct_render_probe_block "overlap_enabled" "overlap-enabled"
		if [[ "${INCLUDE_NATIVE_SPEECH}" == "1" ]]; then
			printf '\n## Lane 3: Native Speech\n\n'
			fct_render_native_note
			fct_render_probe_block "native_speech" "native-speech"
		fi
		printf '\n## Compare Bundles\n\n'
		printf '```bash\n'
		printf 'make compare-ai-voice-latency BUNDLES="%s %s' \
			"${EVIDENCE_ROOT%/}/${DATE_LABEL}-shared-path" \
			"${EVIDENCE_ROOT%/}/${DATE_LABEL}-overlap-enabled"
		if [[ "${INCLUDE_NATIVE_SPEECH}" == "1" ]]; then
			printf ' %s' "${EVIDENCE_ROOT%/}/${DATE_LABEL}-native-speech"
		fi
		printf '"\n```\n'
		printf '\n## Report Template\n\n'
		printf 'Copy [phase40-ai-voice-results-template.md](phase40-ai-voice-results-template.md) into the same evidence directory and fill it in after the comparison step.\n'
	} >"${tmp_path}"

	if [[ -n "${OUTPUT_PATH}" ]]; then
		if [[ -n "${USER_TOKEN}" ]]; then
			fct_log "WARN" "BOTCHECK_USER_TOKEN will be written in plaintext to ${OUTPUT_PATH} — do not commit this file"
		fi
		mkdir -p "$(dirname "${OUTPUT_PATH}")"
		cp "${tmp_path}" "${OUTPUT_PATH}"
		fct_log "INFO" "Benchmark plan written to ${OUTPUT_PATH}"
	fi

	cat "${tmp_path}"
}

fct_main "$@"
