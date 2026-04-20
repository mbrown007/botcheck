#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"

PROM_URL="${BOTCHECK_PROM_URL:-http://localhost:9090}"
RULES_DIR="${BOTCHECK_PROM_RULES_DIR:-infra/observability/alerts}"
RULE_FILE_BASENAME="${BOTCHECK_SIM_RULE_FILE:-zz_phase4_simulation.rules.yml}"
ALERT_NAME="${BOTCHECK_SIM_ALERT_NAME:-BotCheckPhase4SimulationAlert}"
FOR_SECONDS="${BOTCHECK_SIM_ALERT_FOR_S:-30}"
TIMEOUT_SECONDS="${BOTCHECK_SIM_TIMEOUT_S:-120}"
POLL_INTERVAL_S="${BOTCHECK_SIM_POLL_S:-3}"
MAX_TIME_S="${BOTCHECK_HTTP_MAX_TIME_S:-10}"
CONNECT_TIMEOUT_S="${BOTCHECK_HTTP_CONNECT_TIMEOUT_S:-5}"

SIM_RULE_PATH=""


fct_usage() {
	cat <<EOF
${SCRIPT_NAME}
Inject a temporary Prometheus alert rule, verify it reaches FIRING, then clean up.

Usage:
  ${SCRIPT_NAME} [options]

Options:
  --prom-url <url>          Prometheus base URL (default: ${PROM_URL})
  --rules-dir <path>        Prometheus mounted alerts dir (default: ${RULES_DIR})
  --rule-file <name>        Temporary rule file name (default: ${RULE_FILE_BASENAME})
  --alert-name <name>       Simulation alert name (default: ${ALERT_NAME})
  --for-s <seconds>         Alert 'for' duration (default: ${FOR_SECONDS})
  --timeout-s <seconds>     Max wait for FIRING state (default: ${TIMEOUT_SECONDS})
  --poll-s <seconds>        Poll interval while waiting (default: ${POLL_INTERVAL_S})
  -h, --help                Show help
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
		--prom-url)
			PROM_URL="${2:?--prom-url requires a value}"
			shift 2
			;;
		--rules-dir)
			RULES_DIR="${2:?--rules-dir requires a value}"
			shift 2
			;;
		--rule-file)
			RULE_FILE_BASENAME="${2:?--rule-file requires a value}"
			shift 2
			;;
		--alert-name)
			ALERT_NAME="${2:?--alert-name requires a value}"
			shift 2
			;;
		--for-s)
			FOR_SECONDS="${2:?--for-s requires a value}"
			shift 2
			;;
		--timeout-s)
			TIMEOUT_SECONDS="${2:?--timeout-s requires a value}"
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


fct_prom_reload() {
	curl -fsS \
		--max-time "${MAX_TIME_S}" \
		--connect-timeout "${CONNECT_TIMEOUT_S}" \
		-X POST "${PROM_URL%/}/-/reload" >/dev/null
}


fct_check_prometheus_reachable() {
	if ! curl -fsS \
		--max-time "${MAX_TIME_S}" \
		--connect-timeout "${CONNECT_TIMEOUT_S}" \
		"${PROM_URL%/}/-/healthy" >/dev/null 2>&1; then
		fct_log "ERROR" "Prometheus is not reachable at ${PROM_URL}"
		fct_log "ERROR" "Start observability stack first (e.g. docker compose up -d prometheus)"
		exit 1
	fi
}


fct_write_simulation_rule() {
	SIM_RULE_PATH="${RULES_DIR%/}/${RULE_FILE_BASENAME}"
	cat >"${SIM_RULE_PATH}" <<EOF
groups:
  - name: botcheck-phase4-simulation
    interval: 15s
    rules:
      - alert: ${ALERT_NAME}
        expr: vector(1)
        for: ${FOR_SECONDS}s
        labels:
          severity: warning
          service: observability
        annotations:
          summary: "Phase 4 simulation alert"
          description: "Temporary alert used to validate on-call alert flow."
EOF
}


fct_cleanup_simulation_rule() {
	if [[ -n "${SIM_RULE_PATH}" && -f "${SIM_RULE_PATH}" ]]; then
		rm -f "${SIM_RULE_PATH}"
		if fct_prom_reload; then
			fct_log "INFO" "Removed simulation alert rule and reloaded Prometheus"
		else
			fct_log "WARN" "Failed to reload Prometheus during cleanup"
		fi
	fi
}


fct_wait_for_firing() {
	local deadline=$((SECONDS + TIMEOUT_SECONDS))

	while ((SECONDS < deadline)); do
		local payload
		payload="$(
			curl -fsS \
				--max-time "${MAX_TIME_S}" \
				--connect-timeout "${CONNECT_TIMEOUT_S}" \
				"${PROM_URL%/}/api/v1/alerts"
		)"
		if jq -e --arg name "${ALERT_NAME}" '
			.status == "success" and any(.data.alerts[]?; .labels.alertname == $name and .state == "firing")
		' >/dev/null <<<"${payload}"; then
			fct_log "INFO" "Simulation alert reached FIRING state: ${ALERT_NAME}"
			return 0
		fi
		sleep "${POLL_INTERVAL_S}"
	done

	fct_log "ERROR" "Timed out waiting for alert to fire: ${ALERT_NAME}"
	return 1
}


fct_main() {
	fct_parse_args "$@"
	fct_require_command "curl"
	fct_require_command "jq"

	if [[ ! -d "${RULES_DIR}" ]]; then
		fct_log "ERROR" "Rules directory does not exist: ${RULES_DIR}"
		exit 1
	fi

	fct_check_prometheus_reachable
	trap fct_cleanup_simulation_rule EXIT

	fct_write_simulation_rule
	fct_prom_reload
	fct_log "INFO" "Installed simulation alert rule: ${SIM_RULE_PATH}"
	fct_wait_for_firing
	fct_log "INFO" "Phase 4 alert simulation passed"
}


fct_main "$@"
