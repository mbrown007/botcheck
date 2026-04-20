#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_NAME="${0##*/}"

DRILL_DIR="${BOTCHECK_DRILL_DIR:-/tmp/botcheck-drill-$(date +%Y%m%d-%H%M%S)}"
DB_SERVICE="${BOTCHECK_DB_SERVICE:-postgres}"
DB_USER="${BOTCHECK_DB_USER:-botcheck}"
DB_NAME="${BOTCHECK_DB_NAME:-botcheck}"
RESTORE_IMAGE="${BOTCHECK_RESTORE_IMAGE:-postgres:16}"
RESTORE_CONTAINER_NAME="${BOTCHECK_RESTORE_CONTAINER_NAME:-botcheck-restore-db-$$}"
RESTORE_USER="${BOTCHECK_RESTORE_USER:-restore}"
RESTORE_PASSWORD="${BOTCHECK_RESTORE_PASSWORD:-restore}"
RESTORE_DB_NAME="${BOTCHECK_RESTORE_DB_NAME:-restoredb}"
RESTORE_WAIT_S="${BOTCHECK_RESTORE_WAIT_S:-60}"


fct_usage() {
	cat <<EOF
${SCRIPT_NAME}
Run a timed Postgres backup+restore drill and emit evidence artifacts.

Usage:
  ${SCRIPT_NAME} [options]

Options:
  --drill-dir <path>        Output directory (default: ${DRILL_DIR})
  --db-service <name>       Docker compose DB service (default: ${DB_SERVICE})
  --db-user <name>          Source DB user (default: ${DB_USER})
  --db-name <name>          Source DB name (default: ${DB_NAME})
  --restore-image <image>   Restore DB image (default: ${RESTORE_IMAGE})
  --restore-wait-s <secs>   Max wait for restore DB readiness (default: ${RESTORE_WAIT_S})
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
		--drill-dir)
			DRILL_DIR="${2:?--drill-dir requires a value}"
			shift 2
			;;
		--db-service)
			DB_SERVICE="${2:?--db-service requires a value}"
			shift 2
			;;
		--db-user)
			DB_USER="${2:?--db-user requires a value}"
			shift 2
			;;
		--db-name)
			DB_NAME="${2:?--db-name requires a value}"
			shift 2
			;;
		--restore-image)
			RESTORE_IMAGE="${2:?--restore-image requires a value}"
			shift 2
			;;
		--restore-wait-s)
			RESTORE_WAIT_S="${2:?--restore-wait-s requires a value}"
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


fct_cleanup_restore_container() {
	if docker ps -a --format '{{.Names}}' | grep -Fxq "${RESTORE_CONTAINER_NAME}"; then
		docker rm -f "${RESTORE_CONTAINER_NAME}" >/dev/null 2>&1 || true
	fi
}


fct_query_count() {
	local table="${1}"
	docker exec -i "${RESTORE_CONTAINER_NAME}" \
		psql -U "${RESTORE_USER}" -d "${RESTORE_DB_NAME}" -t -A \
		-c "select count(*) from ${table};" | tr -d '[:space:]'
}


fct_collect_artifact_manifest() {
	local out="${DRILL_DIR}/artifacts.ls.txt"
	if docker compose ps --status running minio 2>/dev/null | grep -q "minio"; then
		docker compose exec -T minio mc ls -r local/botcheck-artifacts >"${out}" || true
		fct_log "INFO" "Collected MinIO artifact listing"
		return
	fi

	if command -v aws >/dev/null 2>&1; then
		AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-test}" \
		AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-test}" \
		AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}" \
			aws --endpoint-url="${AWS_ENDPOINT_URL:-http://localhost:4566}" \
				s3 ls s3://botcheck-artifacts --recursive >"${out}" || true
		fct_log "INFO" "Collected AWS/LocalStack artifact listing"
		return
	fi

	fct_log "WARN" "Skipped artifact listing (neither minio service nor aws CLI available)"
}


fct_main() {
	fct_parse_args "$@"
	fct_require_command "docker"
	fct_require_command "sha256sum"
	fct_require_command "date"
	if ! docker compose version >/dev/null 2>&1; then
		fct_log "ERROR" "docker compose is required"
		exit 2
	fi
	if ! docker compose ps --status running "${DB_SERVICE}" 2>/dev/null | grep -q "${DB_SERVICE}"; then
		fct_log "ERROR" "Database service '${DB_SERVICE}' is not running"
		fct_log "ERROR" "Start stack first (e.g. docker compose up -d ${DB_SERVICE})"
		exit 1
	fi

	mkdir -p "${DRILL_DIR}"
	trap fct_cleanup_restore_container EXIT

	local backup_started backup_finished restore_started restore_finished
	backup_started="$(date +%s)"
	docker compose exec -T "${DB_SERVICE}" \
		pg_dump -U "${DB_USER}" -d "${DB_NAME}" >"${DRILL_DIR}/botcheck.sql"
	backup_finished="$(date +%s)"

	sha256sum "${DRILL_DIR}/botcheck.sql" >"${DRILL_DIR}/botcheck.sql.sha256"
	fct_collect_artifact_manifest

	docker run --rm -d \
		--name "${RESTORE_CONTAINER_NAME}" \
		-e "POSTGRES_PASSWORD=${RESTORE_PASSWORD}" \
		-e "POSTGRES_USER=${RESTORE_USER}" \
		-e "POSTGRES_DB=${RESTORE_DB_NAME}" \
		"${RESTORE_IMAGE}" >/dev/null

	local deadline=$((SECONDS + RESTORE_WAIT_S))
	until docker exec "${RESTORE_CONTAINER_NAME}" \
		pg_isready -U "${RESTORE_USER}" -d "${RESTORE_DB_NAME}" >/dev/null 2>&1; do
		if ((SECONDS >= deadline)); then
			fct_log "ERROR" "Restore database did not become ready within ${RESTORE_WAIT_S}s"
			exit 1
		fi
		sleep 1
	done

	restore_started="$(date +%s)"
	cat "${DRILL_DIR}/botcheck.sql" | docker exec -i "${RESTORE_CONTAINER_NAME}" \
		psql -U "${RESTORE_USER}" -d "${RESTORE_DB_NAME}" >/dev/null
	restore_finished="$(date +%s)"

	local runs_count scenarios_count audit_count schedules_count
	runs_count="$(fct_query_count "runs")"
	scenarios_count="$(fct_query_count "scenarios")"
	audit_count="$(fct_query_count "audit_log")"
	schedules_count="$(fct_query_count "schedules")"

	local backup_seconds restore_seconds
	backup_seconds=$((backup_finished - backup_started))
	restore_seconds=$((restore_finished - restore_started))

	cat >"${DRILL_DIR}/summary.env" <<EOF
backup_seconds=${backup_seconds}
restore_seconds=${restore_seconds}
runs_count=${runs_count}
scenarios_count=${scenarios_count}
audit_log_count=${audit_count}
schedules_count=${schedules_count}
drill_dir=${DRILL_DIR}
timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

	fct_log "INFO" "Backup+restore drill completed"
	fct_log "INFO" "backup_seconds=${backup_seconds} restore_seconds=${restore_seconds}"
	fct_log "INFO" "counts runs=${runs_count} scenarios=${scenarios_count} audit_log=${audit_count} schedules=${schedules_count}"
	fct_log "INFO" "Artifacts written to ${DRILL_DIR}"
}


fct_main "$@"
