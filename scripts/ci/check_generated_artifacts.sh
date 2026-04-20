#!/usr/bin/env bash
#
# Validate generated artifacts are up to date.

set -Eeuo pipefail

readonly SCRIPT_VERSION="0.1.0"
readonly SCRIPT_PATH="${BASH_SOURCE[0]}"
readonly SCRIPT_NAME="${SCRIPT_PATH##*/}"

fct_get_repo_root() {
	local script_dir
	script_dir="$(cd "$(dirname "${SCRIPT_PATH}")" >/dev/null 2>&1 && pwd -P)"
	(cd "${script_dir}/../.." >/dev/null 2>&1 && pwd -P)
}

readonly REPO_ROOT="$(fct_get_repo_root)"

fct_check_clean_diff() {
	local pathspec=("$@")
	if ! git -C "${REPO_ROOT}" diff --exit-code -- "${pathspec[@]}" >/dev/null; then
		printf '%s\n' "Generated artifacts are out of date for: ${pathspec[*]}" >&2
		printf '%s\n' "Regenerate them and commit the updated files." >&2
		return 1
	fi
}

fct_check_schemas() {
	printf '%s\n' "Checking JSON schema artifacts..."
	UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}" \
		uv run python "${REPO_ROOT}/scripts/generate_schemas.py"
	fct_check_clean_diff "${REPO_ROOT}/schemas"
}

fct_check_api_types() {
	printf '%s\n' "Checking OpenAPI and generated API types..."
	npm --prefix "${REPO_ROOT}/web" run gen:api-types
	fct_check_clean_diff \
		"${REPO_ROOT}/web/src/lib/api/openapi.json" \
		"${REPO_ROOT}/web/src/lib/api/generated.ts"
}

fct_main() {
	cd "${REPO_ROOT}"
	fct_check_schemas
	fct_check_api_types
	printf '%s\n' "Generated artifacts are up to date."
}

fct_main "$@"
