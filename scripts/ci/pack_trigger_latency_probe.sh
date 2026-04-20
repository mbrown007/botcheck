#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"

API_URL="${BOTCHECK_API_URL:-http://localhost:7700}"
PACK_ID="${BOTCHECK_PACK_ID:-}"
USER_TOKEN="${BOTCHECK_USER_TOKEN:-}"
SAMPLES="${BOTCHECK_PACK_TRIGGER_SAMPLES:-3}"
MAX_MS="${BOTCHECK_PACK_TRIGGER_MAX_MS:-500}"
CANCEL_AFTER_TRIGGER="${BOTCHECK_PACK_TRIGGER_CANCEL_AFTER:-true}"
EVIDENCE_DIR="${BOTCHECK_PACK_TRIGGER_EVIDENCE_DIR:-}"

fct_usage() {
	cat <<EOF_USAGE
${SCRIPT_NAME}
Measure POST /packs/{id}/run latency and enforce a response-time budget.

Usage:
  ${SCRIPT_NAME} --pack-id <id> --user-token <token> [options]

Options:
  --api-url <url>          BotCheck API base URL (default: ${API_URL})
  --pack-id <id>           Pack ID to trigger
  --user-token <token>     User bearer token
  --samples <n>            Number of trigger samples to record (default: ${SAMPLES})
  --max-ms <n>             Maximum allowed latency in milliseconds (default: ${MAX_MS})
  --cancel-after <bool>    Cancel each pack run after trigger (default: ${CANCEL_AFTER_TRIGGER})
  --evidence-dir <path>    Optional directory to write probe artifacts
  -h, --help               Show help and exit
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
		--samples)
			SAMPLES="${2:?--samples requires a value}"
			shift 2
			;;
		--max-ms)
			MAX_MS="${2:?--max-ms requires a value}"
			shift 2
			;;
		--cancel-after)
			CANCEL_AFTER_TRIGGER="${2:?--cancel-after requires a value}"
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

fct_cancel_pack_run_best_effort() {
	local pack_run_id="${1}"
	curl -sS \
		-X POST \
		-H "Authorization: Bearer ${USER_TOKEN}" \
		"${API_URL%/}/pack-runs/${pack_run_id}/cancel" >/dev/null || true
}

fct_main() {
	fct_parse_args "$@"
	fct_require_command "curl"
	fct_require_command "jq"
	fct_require_command "awk"
	fct_require_command "sort"

	[[ -n "${PACK_ID}" ]] || { fct_log "ERROR" "--pack-id is required"; exit 2; }
	[[ -n "${USER_TOKEN}" ]] || { fct_log "ERROR" "--user-token is required"; exit 2; }
	[[ "${SAMPLES}" =~ ^[0-9]+$ ]] || { fct_log "ERROR" "--samples must be a positive integer"; exit 2; }
	[[ "${SAMPLES}" -ge 1 ]] || { fct_log "ERROR" "--samples must be >= 1"; exit 2; }
	[[ "${MAX_MS}" =~ ^[0-9]+$ ]] || { fct_log "ERROR" "--max-ms must be a positive integer"; exit 2; }
	[[ "${MAX_MS}" -ge 1 ]] || { fct_log "ERROR" "--max-ms must be >= 1"; exit 2; }

	local work_dir latencies_path
	work_dir="$(mktemp -d)"
	latencies_path="${work_dir}/latencies_ms.txt"
	trap 'rm -rf "${work_dir}"' EXIT

	local i
	for i in $(seq 1 "${SAMPLES}"); do
		local idempotency_key response body status elapsed_s elapsed_ms pack_run_id
		idempotency_key="pack-latency-${PACK_ID}-${i}-$(date +%s%N)"
		response="$(curl -sS \
			-X POST \
			-H "Authorization: Bearer ${USER_TOKEN}" \
			-H "Idempotency-Key: ${idempotency_key}" \
			"${API_URL%/}/packs/${PACK_ID}/run" \
			-w $'\n%{http_code}\n%{time_total}')"
		body="$(printf '%s' "${response}" | sed -n '1p')"
		status="$(printf '%s' "${response}" | sed -n '2p')"
		elapsed_s="$(printf '%s' "${response}" | sed -n '3p')"
		elapsed_ms="$(awk -v seconds="${elapsed_s}" 'BEGIN { printf "%.3f", seconds * 1000 }')"

		if [[ "${status}" != "202" ]]; then
			fct_log "ERROR" "Trigger failed sample=${i} status=${status} body=${body}"
			exit 1
		fi
		printf '%s\n' "${elapsed_ms}" >>"${latencies_path}"
		pack_run_id="$(printf '%s' "${body}" | jq -r '.pack_run_id // empty')"
		fct_log "INFO" "sample=${i}/${SAMPLES} latency_ms=${elapsed_ms} pack_run_id=${pack_run_id}"
		if [[ "${CANCEL_AFTER_TRIGGER}" == "true" && -n "${pack_run_id}" ]]; then
			fct_cancel_pack_run_best_effort "${pack_run_id}"
		fi
	done

	local count max_ms_observed avg_ms p95_ms rank
	count="$(wc -l <"${latencies_path}" | tr -d ' ')"
	max_ms_observed="$(sort -n "${latencies_path}" | tail -n1)"
	avg_ms="$(awk '{sum += $1} END { if (NR == 0) { print "0.000" } else { printf "%.3f", sum / NR } }' "${latencies_path}")"
	rank="$(awk -v n="${count}" 'BEGIN { r = int((95 * n + 99) / 100); if (r < 1) r = 1; print r }')"
	p95_ms="$(sort -n "${latencies_path}" | sed -n "${rank}p")"

	if awk -v observed="${max_ms_observed}" -v limit="${MAX_MS}" 'BEGIN { exit !(observed <= limit) }'; then
		fct_log "INFO" "Pack trigger latency probe passed (max_ms=${max_ms_observed}, p95_ms=${p95_ms}, avg_ms=${avg_ms}, limit_ms=${MAX_MS})"
	else
		fct_log "ERROR" "Pack trigger latency exceeded limit (max_ms=${max_ms_observed}, limit_ms=${MAX_MS})"
		exit 1
	fi

	if [[ -n "${EVIDENCE_DIR}" ]]; then
		mkdir -p "${EVIDENCE_DIR}"
		cp "${latencies_path}" "${EVIDENCE_DIR%/}/pack_trigger_latency_samples.txt"
		jq -n \
			--arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
			--arg api_url "${API_URL}" \
			--arg pack_id "${PACK_ID}" \
			--argjson samples "${SAMPLES}" \
			--argjson max_budget_ms "${MAX_MS}" \
			--argjson max_observed_ms "${max_ms_observed}" \
			--argjson p95_ms "${p95_ms}" \
			--argjson avg_ms "${avg_ms}" \
			'{
				generated_at: $generated_at,
				api_url: $api_url,
				pack_id: $pack_id,
				samples: $samples,
				max_budget_ms: $max_budget_ms,
				max_observed_ms: $max_observed_ms,
				p95_ms: $p95_ms,
				avg_ms: $avg_ms
			}' >"${EVIDENCE_DIR%/}/pack_trigger_latency_summary.json"
		fct_log "INFO" "Evidence written to ${EVIDENCE_DIR%/}"
	fi
}

fct_main "$@"
