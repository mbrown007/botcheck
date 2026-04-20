#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"
readonly SCRIPT_DIR="$(cd "${0%/*}" >/dev/null 2>&1 && pwd -P)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd -P)"

API_URL="${BOTCHECK_API_URL:-http://localhost:7700}"
USER_TOKEN="${BOTCHECK_TOKEN:-${BOTCHECK_USER_TOKEN:-}}"
MONITORING_ASSISTANT_API_URL="${MONITORING_ASSISTANT_API_URL:-http://localhost:18081}"
DESTINATION_NAME="${DESTINATION_NAME:-Monitoring Assistant Local SSE}"
TMP_DIR=""

fct_usage() {
	cat <<EOF_USAGE
${SCRIPT_NAME}
Create a direct HTTP destination, upload monitoring-assistant graph scenarios,
create the matching pack, and import the monitoring-assistant Grai eval suites.

Usage:
  ${SCRIPT_NAME} --user-token <token> [options]

Options:
  --api-url <url>                    BotCheck API base URL (default: ${API_URL})
  --user-token <token>               BotCheck bearer token
  --assistant-api-url <url>          Monitoring assistant base URL (default: ${MONITORING_ASSISTANT_API_URL})
  --destination-name <name>          Destination display name (default: ${DESTINATION_NAME})
  -h, --help                         Show help and exit

Environment:
  BOTCHECK_API_URL
  BOTCHECK_TOKEN or BOTCHECK_USER_TOKEN
  MONITORING_ASSISTANT_API_URL
  DESTINATION_NAME
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
		--assistant-api-url)
			MONITORING_ASSISTANT_API_URL="${2:?--assistant-api-url requires a value}"
			shift 2
			;;
		--destination-name)
			DESTINATION_NAME="${2:?--destination-name requires a value}"
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

fct_post_json() {
	local path="${1}"
	local payload_path="${2}"

	curl -fsS \
		-X POST \
		-H "Authorization: Bearer ${USER_TOKEN}" \
		-H "Content-Type: application/json" \
		"${API_URL%/}${path}" \
		--data @"${payload_path}"
}

fct_upload_yaml_as_json() {
	local path="${1}"
	local tmp_payload="${TMP_DIR}/$(basename "${path}").json"

	jq -Rs '{yaml_content: .}' <"${path}" >"${tmp_payload}"
	fct_post_json "$2" "${tmp_payload}"
}

fct_create_destination() {
	local template_path="${REPO_ROOT}/scenarios/transport-profiles/examples/monitoring-assistant-local-sse.json"
	local payload_path="${TMP_DIR}/destination.json"

	jq \
		--arg endpoint "${MONITORING_ASSISTANT_API_URL%/}/api/chat" \
		--arg name "${DESTINATION_NAME}" \
		'.endpoint = $endpoint | .name = $name' \
		"${template_path}" >"${payload_path}"

	fct_post_json "/destinations/" "${payload_path}"
}

fct_upload_scenarios() {
	local scenario_path
	for scenario_path in \
		"${REPO_ROOT}/scenarios/examples/monitoring-assistant-dashboard-handoff.yaml" \
		"${REPO_ROOT}/scenarios/examples/monitoring-assistant-anomaly-ranking.yaml" \
		"${REPO_ROOT}/scenarios/examples/monitoring-assistant-query-help.yaml" \
		"${REPO_ROOT}/scenarios/examples/monitoring-assistant-incident-triage.yaml" \
		"${REPO_ROOT}/scenarios/examples/monitoring-assistant-runbook-guidance.yaml"; do
		fct_log "INFO" "Uploading scenario $(basename "${scenario_path}")"
		fct_upload_yaml_as_json "${scenario_path}" "/scenarios/" >/dev/null
	done
}

fct_create_pack() {
	local payload_path="${REPO_ROOT}/scenarios/packs/examples/monitoring-assistant-http-pack.json"
	fct_post_json "/packs/" "${payload_path}"
}

fct_import_grai_suite() {
	local suite_path="${1}"
	fct_upload_yaml_as_json "${suite_path}" "/grai/suites/import"
}

fct_main() {
	fct_parse_args "$@"
	fct_require_command "curl"
	fct_require_command "jq"

	[[ -n "${USER_TOKEN}" ]] || {
		fct_log "ERROR" "--user-token is required (or set BOTCHECK_TOKEN/BOTCHECK_USER_TOKEN)"
		exit 2
	}

	TMP_DIR="$(mktemp -d)"
	trap 'rm -rf "${TMP_DIR}"' EXIT

	local destination_resp pack_resp targeted_suite_resp alert_suite_resp destination_id pack_id targeted_suite_id alert_suite_id

	fct_log "INFO" "Creating monitoring assistant HTTP destination"
	destination_resp="$(fct_create_destination)"
	destination_id="$(printf '%s' "${destination_resp}" | jq -r '.destination_id')"

	fct_upload_scenarios

	fct_log "INFO" "Creating monitoring assistant pack"
	pack_resp="$(fct_create_pack)"
	pack_id="$(printf '%s' "${pack_resp}" | jq -r '.pack_id')"

	fct_log "INFO" "Importing monitoring assistant targeted-task Grai suite"
	targeted_suite_resp="$(fct_import_grai_suite "${REPO_ROOT}/grai/examples/monitoring-assistant-targeted-tasks.promptfoo.yaml")"
	targeted_suite_id="$(printf '%s' "${targeted_suite_resp}" | jq -r '.suite_id')"

	fct_log "INFO" "Importing monitoring assistant alert-investigation Grai suite"
	alert_suite_resp="$(fct_import_grai_suite "${REPO_ROOT}/grai/examples/monitoring-assistant-alert-investigations.promptfoo.yaml")"
	alert_suite_id="$(printf '%s' "${alert_suite_resp}" | jq -r '.suite_id')"

	jq -n \
		--arg api_url "${API_URL%/}" \
		--arg monitoring_assistant_api_url "${MONITORING_ASSISTANT_API_URL%/}/api/chat" \
		--arg destination_id "${destination_id}" \
		--arg pack_id "${pack_id}" \
		--arg targeted_suite_id "${targeted_suite_id}" \
		--arg alert_suite_id "${alert_suite_id}" \
		'{
			api_url: $api_url,
			monitoring_assistant_api_url: $monitoring_assistant_api_url,
			destination_id: $destination_id,
			transport_profile_id: $destination_id,
			pack_id: $pack_id,
			suite_ids: {
				targeted_tasks: $targeted_suite_id,
				alert_investigations: $alert_suite_id
			}
		}'
}

fct_main "$@"
