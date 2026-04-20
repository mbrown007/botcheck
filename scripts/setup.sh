#!/usr/bin/env bash
#
# ==============================================================================
# BotCheck — Server Setup Script
# ==============================================================================
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Brownster/botcheck/main/scripts/setup.sh | bash
#   bash setup.sh [--dev] [--dir PATH] [--help]
#
# Flags:
#   --dev        Use local dev defaults (devkey/devsecret, no TLS prompts)
#   --dir PATH   Install into PATH instead of ~/botcheck
#   -h, --help   Show this help
#
# Idempotent: safe to re-run on an existing installation.
# Supports: Ubuntu 22.04+, Debian 12+, Fedora 38+
# ==============================================================================

readonly SCRIPT_VERSION="1.0.0"
readonly SCRIPT_NAME="${BASH_SOURCE[0]##*/}"
readonly BOTCHECK_REPO="https://github.com/Brownster/botcheck.git"
readonly LIVEKIT_SIP_IMAGE="livekit/sip:latest"
readonly LK_CLI_REPO="livekit/livekit-cli"

# ==============================================================================
# Runtime state
# ==============================================================================

DEV_MODE=false
INSTALL_DIR="${HOME}/botcheck"
TMP_DIR=""

# Collected config (populated by prompts or existing .env)
CFG_COMPANY_NAME=""
CFG_ADMIN_EMAIL=""
CFG_ADMIN_PASSWORD=""
CFG_OPENAI_API_KEY=""
CFG_DEEPGRAM_API_KEY=""
CFG_ANTHROPIC_API_KEY=""
CFG_SIP_USERNAME=""
CFG_SIP_PASSWORD=""
CFG_SIP_PROVIDER="sipgate.co.uk"
CFG_SIP_ALLOWLIST="sipgate.co.uk"
CFG_ENABLE_SIP=false
CFG_LK_API_KEY="devkey"
CFG_LK_API_SECRET="devsecret00000000000000000000000"
CFG_POSTGRES_PASSWORD=""
CFG_SECRET_KEY=""
CFG_SCHEDULER_SECRET=""
# Production-only
CFG_API_DOMAIN=""
CFG_LK_DOMAIN=""
CFG_ACME_EMAIL=""

# ==============================================================================
# Strict mode + traps
# ==============================================================================

set -Eeuo pipefail

cleanup() {
    local exit_status=$?
    set +e
    [[ -n "${TMP_DIR}" && -d "${TMP_DIR}" ]] && rm -rf "${TMP_DIR}"
    return "${exit_status}"
}

on_error() {
    local exit_status=$?
    local line_no="${1:-?}"
    trap - ERR
    log_error "Failed at line ${line_no} (exit ${exit_status})"
    exit "${exit_status}"
}

trap 'cleanup' EXIT
trap 'on_error "${LINENO}"' ERR
trap 'log_warn "Interrupted."; exit 130' INT TERM

# ==============================================================================
# Logging
# ==============================================================================

_ansi() { [[ -t 2 ]] && printf '\033[%sm' "${1}" || true; }

log_info()  { printf '%s %s\n' "$(_ansi '32')[INFO]$(_ansi '0')"  "$*" >&2; }
log_warn()  { printf '%s %s\n' "$(_ansi '33')[WARN]$(_ansi '0')"  "$*" >&2; }
log_error() { printf '%s %s\n' "$(_ansi '31')[ERROR]$(_ansi '0')" "$*" >&2; }
log_step()  { printf '\n%s %s %s\n' "$(_ansi '36')──────$(_ansi '0')" "$(_ansi '1')${*}$(_ansi '0')" "$(_ansi '36')──────$(_ansi '0')" >&2; }

die() { log_error "${1:-Unknown error}"; exit "${2:-1}"; }

# ==============================================================================
# Usage
# ==============================================================================

usage() {
    cat >&2 <<EOF
${SCRIPT_NAME} v${SCRIPT_VERSION} — BotCheck server setup

Usage:
  ${SCRIPT_NAME} [--dev] [--dir PATH]

Flags:
  --dev        Use local dev defaults (devkey/devsecret, skip TLS/domain prompts)
  --dir PATH   Install into PATH  (default: ~/botcheck)
  -h, --help   Show this help

Examples:
  # Local dev machine
  bash setup.sh --dev

  # Production server
  bash setup.sh --dir /opt/botcheck
EOF
}

# ==============================================================================
# Argument parsing
# ==============================================================================

fct_parse_args() {
    while [[ $# -gt 0 ]]; do
        case "${1}" in
            --dev)        DEV_MODE=true; shift ;;
            --dir)        [[ $# -lt 2 ]] && die "--dir requires a path"; INSTALL_DIR="${2}"; shift 2 ;;
            --dir=*)      INSTALL_DIR="${1#*=}"; shift ;;
            -h|--help)    usage; exit 0 ;;
            *)            die "Unknown option: ${1}" 2 ;;
        esac
    done
}

# ==============================================================================
# OS detection
# ==============================================================================

OS_ID=""
OS_FAMILY=""  # debian | fedora

fct_detect_os() {
    if [[ -f /etc/os-release ]]; then
        # shellcheck source=/dev/null
        source /etc/os-release
        OS_ID="${ID:-unknown}"
    else
        die "Cannot detect OS — /etc/os-release not found."
    fi

    case "${OS_ID}" in
        ubuntu|debian)  OS_FAMILY="debian" ;;
        fedora|rhel|centos|rocky|almalinux) OS_FAMILY="fedora" ;;
        *) die "Unsupported OS: ${OS_ID}. Supported: Ubuntu, Debian, Fedora." ;;
    esac

    log_info "Detected OS: ${OS_ID} (${OS_FAMILY})"
}

# ==============================================================================
# Prerequisite tools
# ==============================================================================

fct_install_prerequisites() {
    log_step "Installing prerequisites"

    if [[ "${OS_FAMILY}" == "debian" ]]; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq curl git jq openssl python3
    else
        sudo dnf install -y -q curl git jq openssl python3
    fi
}

# ==============================================================================
# Docker
# ==============================================================================

fct_install_docker() {
    log_step "Docker"

    if command -v docker &>/dev/null && docker compose version &>/dev/null; then
        log_info "Docker + Compose already installed — skipping."
        return
    fi

    log_info "Installing Docker..."

    if [[ "${OS_FAMILY}" == "debian" ]]; then
        sudo apt-get install -y -qq ca-certificates gnupg lsb-release
        sudo install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
            | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        sudo chmod a+r /etc/apt/keyrings/docker.gpg
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
            | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
        sudo apt-get update -qq
        sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    else
        sudo dnf -y -q install dnf-plugins-core
        sudo dnf config-manager --add-repo https://download.docker.com/linux/fedora/docker-ce.repo
        sudo dnf install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin
    fi

    sudo systemctl enable --now docker
    sudo usermod -aG docker "${USER}"
    log_warn "Added ${USER} to docker group. You may need to log out and back in if this is a fresh install."
}

# ==============================================================================
# LiveKit CLI (lk)
# ==============================================================================

fct_install_lk_cli() {
    log_step "LiveKit CLI (lk)"

    if command -v lk &>/dev/null; then
        log_info "lk already installed at $(command -v lk) — skipping."
        return
    fi

    log_info "Installing lk CLI..."

    local arch
    arch="$(uname -m)"
    local asset_arch
    case "${arch}" in
        x86_64)  asset_arch="amd64" ;;
        aarch64) asset_arch="arm64" ;;
        *)        die "Unsupported architecture: ${arch}" ;;
    esac

    local download_url
    download_url="$(curl -s "https://api.github.com/repos/${LK_CLI_REPO}/releases" \
        | jq -r ".[0].assets[] | select(.name | test(\"linux_${asset_arch}.tar.gz\")) | .browser_download_url" \
        | head -1)"

    [[ -z "${download_url}" ]] && die "Could not find lk CLI download URL."

    curl -fsSL "${download_url}" | tar -xz -C "${TMP_DIR}"
    sudo install -m 0755 "${TMP_DIR}/lk" /usr/local/bin/lk
    log_info "lk installed: $(lk --version 2>/dev/null || echo 'ok')"
}

# ==============================================================================
# Clone / update repo
# ==============================================================================

fct_clone_or_update_repo() {
    log_step "BotCheck repository"

    if [[ -d "${INSTALL_DIR}/.git" ]]; then
        log_info "Repo already at ${INSTALL_DIR} — pulling latest."
        git -C "${INSTALL_DIR}" pull --ff-only || log_warn "git pull failed — continuing with existing code."
    else
        log_info "Cloning into ${INSTALL_DIR}..."
        git clone "${BOTCHECK_REPO}" "${INSTALL_DIR}"
    fi
}

# ==============================================================================
# Prompt helpers
# ==============================================================================

# fct_prompt VAR "prompt text" "default" secret?
fct_prompt() {
    local var_name="${1}"
    local prompt_text="${2}"
    local default="${3:-}"
    local secret="${4:-false}"

    local display_default=""
    if [[ -n "${default}" ]]; then
        if [[ "${secret}" == "true" ]]; then
            display_default=" [****]"
        else
            display_default=" [${default}]"
        fi
    fi

    local value=""
    if [[ "${secret}" == "true" ]]; then
        read -r -s -p "  ${prompt_text}${display_default}: " value
        printf '\n'
    else
        read -r -p "  ${prompt_text}${display_default}: " value
    fi

    if [[ -z "${value}" && -n "${default}" ]]; then
        value="${default}"
    fi

    printf -v "${var_name}" '%s' "${value}"
}

fct_prompt_yn() {
    local var_name="${1}"
    local prompt_text="${2}"
    local default="${3:-n}"

    local answer
    read -r -p "  ${prompt_text} [y/N]: " answer
    answer="${answer:-${default}}"
    if [[ "${answer}" =~ ^[Yy] ]]; then
        printf -v "${var_name}" '%s' "true"
    else
        printf -v "${var_name}" '%s' "false"
    fi
}

# ==============================================================================
# Load existing .env values as defaults
# ==============================================================================

fct_load_existing_env() {
    local env_file="${INSTALL_DIR}/.env"
    [[ -f "${env_file}" ]] || return 0

    log_info "Found existing .env — loading as defaults."

    _env_val() {
        grep -E "^${1}=" "${env_file}" 2>/dev/null | cut -d= -f2- | tr -d '"' || true
    }

    CFG_OPENAI_API_KEY="$(_env_val OPENAI_API_KEY)"
    CFG_DEEPGRAM_API_KEY="$(_env_val DEEPGRAM_API_KEY)"
    CFG_ANTHROPIC_API_KEY="$(_env_val ANTHROPIC_API_KEY)"
    CFG_SIP_USERNAME="$(_env_val SIP_AUTH_USERNAME)"
    CFG_SIP_PASSWORD="$(_env_val SIP_AUTH_PASSWORD)"
    CFG_SIP_PROVIDER="$(_env_val SIP_PROVIDER)"
    CFG_SIP_ALLOWLIST="$(_env_val SIP_DESTINATION_ALLOWLIST)"
    CFG_LK_API_KEY="$(_env_val LIVEKIT_API_KEY)"
    CFG_LK_API_SECRET="$(_env_val LIVEKIT_API_SECRET)"
    CFG_POSTGRES_PASSWORD="$(_env_val POSTGRES_PASSWORD)"
    CFG_SECRET_KEY="$(_env_val SECRET_KEY)"
    CFG_SCHEDULER_SECRET="$(_env_val SCHEDULER_SECRET)"
    CFG_ADMIN_EMAIL="$(_env_val LOCAL_AUTH_EMAIL)"
    CFG_ADMIN_PASSWORD="$(_env_val LOCAL_AUTH_PASSWORD)"
    CFG_API_DOMAIN="$(_env_val API_DOMAIN)"
    CFG_LK_DOMAIN="$(_env_val LIVEKIT_DOMAIN)"
    CFG_ACME_EMAIL="$(_env_val ACME_EMAIL)"

    local enable_sip
    enable_sip="$(_env_val ENABLE_OUTBOUND_SIP)"
    [[ "${enable_sip}" == "true" ]] && CFG_ENABLE_SIP=true || true
}

# ==============================================================================
# Interactive prompts
# ==============================================================================

fct_prompt_configuration() {
    log_step "Configuration"

    printf '\n%s\n\n' "$(_ansi '1')Press Enter to accept defaults shown in [brackets].$(_ansi '0')"

    # ── Identity ──────────────────────────────────────────────────────────────
    printf '%s\n' "$(_ansi '1')── Instance identity ──$(_ansi '0')"
    fct_prompt CFG_COMPANY_NAME "Company / tenant name" "${CFG_COMPANY_NAME}"
    fct_prompt CFG_ADMIN_EMAIL  "Admin email"           "${CFG_ADMIN_EMAIL:-admin@botcheck.local}"

    if [[ "${DEV_MODE}" == "true" ]]; then
        CFG_ADMIN_PASSWORD="${CFG_ADMIN_PASSWORD:-botcheck-dev-password}"
        log_info "Dev mode: using default admin password."
    else
        fct_prompt CFG_ADMIN_PASSWORD "Admin password" "${CFG_ADMIN_PASSWORD}" true
        [[ -z "${CFG_ADMIN_PASSWORD}" ]] && die "Admin password is required."
    fi

    # ── AI API keys ───────────────────────────────────────────────────────────
    printf '\n%s\n' "$(_ansi '1')── AI API keys ──$(_ansi '0')"
    fct_prompt CFG_OPENAI_API_KEY    "OpenAI API key"    "${CFG_OPENAI_API_KEY}"    true
    fct_prompt CFG_DEEPGRAM_API_KEY  "Deepgram API key"  "${CFG_DEEPGRAM_API_KEY}"  true
    fct_prompt CFG_ANTHROPIC_API_KEY "Anthropic API key" "${CFG_ANTHROPIC_API_KEY}" true

    # ── SIP ───────────────────────────────────────────────────────────────────
    printf '\n%s\n' "$(_ansi '1')── SIP / telephony ──$(_ansi '0')"
    fct_prompt_yn CFG_ENABLE_SIP "Enable outbound SIP (requires sipgate or similar trunk)?" \
        "$( [[ "${CFG_ENABLE_SIP}" == "true" ]] && printf 'y' || printf 'n' )"

    if [[ "${CFG_ENABLE_SIP}" == "true" ]]; then
        fct_prompt CFG_SIP_PROVIDER  "SIP provider domain" "${CFG_SIP_PROVIDER:-sipgate.co.uk}"
        fct_prompt CFG_SIP_USERNAME  "SIP username"        "${CFG_SIP_USERNAME}"
        fct_prompt CFG_SIP_PASSWORD  "SIP password"        "${CFG_SIP_PASSWORD}" true
        fct_prompt CFG_SIP_ALLOWLIST "SIP destination allowlist (comma-separated domains)" \
            "${CFG_SIP_ALLOWLIST:-${CFG_SIP_PROVIDER}}"
    fi

    # ── LiveKit credentials (prod only — dev uses fixed devkey) ───────────────
    if [[ "${DEV_MODE}" == "false" ]]; then
        printf '\n%s\n' "$(_ansi '1')── LiveKit credentials ──$(_ansi '0')"
        CFG_LK_API_KEY="${CFG_LK_API_KEY:-devkey}"
        CFG_LK_API_SECRET="${CFG_LK_API_SECRET:-$(openssl rand -hex 20)}"
        fct_prompt CFG_LK_API_KEY    "LiveKit API key"    "${CFG_LK_API_KEY}"
        fct_prompt CFG_LK_API_SECRET "LiveKit API secret" "${CFG_LK_API_SECRET}" true
    fi

    # ── Production domains (prod only) ────────────────────────────────────────
    if [[ "${DEV_MODE}" == "false" ]]; then
        printf '\n%s\n' "$(_ansi '1')── Production domains (leave blank for local-only) ──$(_ansi '0')"
        fct_prompt CFG_API_DOMAIN  "API domain (e.g. api.example.com)"       "${CFG_API_DOMAIN}"
        fct_prompt CFG_LK_DOMAIN   "LiveKit domain (e.g. livekit.example.com)" "${CFG_LK_DOMAIN}"
        fct_prompt CFG_ACME_EMAIL  "ACME/Let's Encrypt email"                "${CFG_ACME_EMAIL}"
    fi

    # ── Generate secrets if not set ───────────────────────────────────────────
    [[ -z "${CFG_POSTGRES_PASSWORD}" ]]  && CFG_POSTGRES_PASSWORD="$(openssl rand -hex 16)"
    [[ -z "${CFG_SECRET_KEY}" ]]         && CFG_SECRET_KEY="$(openssl rand -hex 32)"
    [[ -z "${CFG_SCHEDULER_SECRET}" ]]   && CFG_SCHEDULER_SECRET="$(openssl rand -hex 16)"
}

# ==============================================================================
# Write .env
# ==============================================================================

fct_write_env() {
    log_step "Writing .env"

    local env_file="${INSTALL_DIR}/.env"
    local lk_url="ws://localhost:7880"

    [[ -n "${CFG_LK_DOMAIN}" ]] && lk_url="wss://${CFG_LK_DOMAIN}"

    local api_domain="${CFG_API_DOMAIN:-api.botchecker.dev}"
    local lk_domain="${CFG_LK_DOMAIN:-livekit.botchecker.dev}"
    local acme_email="${CFG_ACME_EMAIL:-admin@example.com}"

    cat > "${env_file}" <<EOF
# Generated by setup.sh v${SCRIPT_VERSION} on $(date -u '+%Y-%m-%d %H:%M UTC')
# Re-run setup.sh to update — do not commit this file.

# ── Database ─────────────────────────────────────────────────────────────────
POSTGRES_PASSWORD=${CFG_POSTGRES_PASSWORD}

# ── Object Storage (MinIO / S3) ───────────────────────────────────────────────
MINIO_ROOT_USER=botcheck
MINIO_ROOT_PASSWORD=$(openssl rand -hex 16)

# ── LiveKit ──────────────────────────────────────────────────────────────────
LIVEKIT_URL=${lk_url}
LIVEKIT_API_KEY=${CFG_LK_API_KEY}
LIVEKIT_API_SECRET=${CFG_LK_API_SECRET}

# ── BotCheck API ─────────────────────────────────────────────────────────────
SECRET_KEY=${CFG_SECRET_KEY}
SCHEDULER_SECRET=${CFG_SCHEDULER_SECRET}
LOCAL_AUTH_ENABLED=true
LOCAL_AUTH_EMAIL=${CFG_ADMIN_EMAIL}
LOCAL_AUTH_PASSWORD=${CFG_ADMIN_PASSWORD}
LOCAL_AUTH_PASSWORD_HASH=
LOCAL_AUTH_TOKEN_TTL_S=900
LOCAL_AUTH_REFRESH_TOKEN_TTL_S=28800
LOCAL_AUTH_RATE_LIMIT_ATTEMPTS=10
LOCAL_AUTH_RATE_LIMIT_WINDOW_S=60
LOCAL_AUTH_LOCKOUT_FAILED_ATTEMPTS=5
LOCAL_AUTH_LOCKOUT_DURATION_S=900
AUTH_TOTP_CHALLENGE_TTL_S=300
AUTH_TOTP_STEP_S=30
AUTH_TOTP_WINDOW=1
AUTH_TOTP_REPLAY_TTL_S=120
AUTH_SECURITY_REDIS_ENABLED=true
AUTH_SECURITY_REDIS_PREFIX=botcheck:authsec
AUTH_SECURITY_REDIS_TIMEOUT_S=0.2
AUTH_SECURITY_REDIS_FAILURE_BACKOFF_S=5
AUTH_TOTP_ENCRYPTION_KEY=
USERS_BOOTSTRAP_ENABLED=true
USERS_BOOTSTRAP_PATH=services/api/botcheck_api/users.yaml
NEXT_PUBLIC_DEV_USER_TOKEN=
INSTANCE_TIMEZONE=UTC
DEFAULT_RETENTION_PROFILE=standard
SHARED_INSTANCE_MODE=false
TENANT_SWITCHER_ALLOWED_ROLES=admin

# ── External AI APIs ─────────────────────────────────────────────────────────
OPENAI_API_KEY=${CFG_OPENAI_API_KEY}
DEEPGRAM_API_KEY=${CFG_DEEPGRAM_API_KEY}
ANTHROPIC_API_KEY=${CFG_ANTHROPIC_API_KEY}

# ── Outbound SIP ─────────────────────────────────────────────────────────────
ENABLE_OUTBOUND_SIP=${CFG_ENABLE_SIP}
SIP_SECRET_PROVIDER=env
ALLOW_ENV_SIP_SECRETS_IN_PRODUCTION=true
SIP_SECRET_CACHE_TTL_S=60
SIP_TRUNK_ID=
SIP_AUTH_USERNAME=${CFG_SIP_USERNAME}
SIP_AUTH_PASSWORD=${CFG_SIP_PASSWORD}
SIP_SECRET_REF=
SIP_SECRET_REGION=us-east-1
SIP_SECRET_TIMEOUT_S=5
SIP_PROVIDER=${CFG_SIP_PROVIDER}
BOT_SIP_URI=sip:bot@${CFG_SIP_PROVIDER}
BOT_SIP_USER=bot
SIP_DESTINATION_ALLOWLIST=${CFG_SIP_ALLOWLIST}
MAX_CONCURRENT_OUTBOUND_CALLS=5
SIP_DISPATCH_SLOT_TTL_S=900
SCHEDULE_DISPATCH_BACKOFF_S=15
SCHEDULE_DISPATCH_BACKOFF_JITTER_S=5
SCHEDULE_DISPATCH_MAX_ATTEMPTS=5

# ── Metrics / Observability ──────────────────────────────────────────────────
LOG_LEVEL=INFO
LOG_JSON=true
JUDGE_METRICS_ENABLED=true
JUDGE_METRICS_PORT=9101
RETENTION_SWEEP_ENABLED=true
RETENTION_SWEEP_DRY_RUN=false
RETENTION_SWEEP_LIMIT=500
SCHEDULE_TICK_ENABLED=true
SCHEDULE_TICK_LIMIT=50
AGENT_METRICS_ENABLED=true
AGENT_METRICS_PORT=9102
FINAL_ACK_RECOVERY_ENABLED=true
FINAL_ACK_RECOVERY_LOG_PATH=/tmp/botcheck-agent-final-ack-recovery.jsonl
TTS_CACHE_ENABLED=true
TTS_CACHE_PCM_FORMAT_VERSION=v1
TTS_PREVIEW_RATE_LIMIT_ATTEMPTS=30
TTS_PREVIEW_RATE_LIMIT_WINDOW_S=60
TTS_PREVIEW_OPENAI_MODEL=gpt-4o-mini-tts
TTS_PREVIEW_REQUEST_TIMEOUT_S=20
S3_BUCKET_PREFIX=botcheck-artifacts
MULTI_SAMPLE_JUDGE=false
MULTI_SAMPLE_JUDGE_N=3
SCENARIO_GENERATOR_RATE_LIMIT_PER_HOUR=10
SCENARIO_GENERATOR_MODEL=claude-sonnet-4-5-20251001
BOTCHECK_API_URL=http://localhost:7700
BOTCHECK_GATE_TIMEOUT_S=900
BOTCHECK_GATE_POLL_S=5

# ── Grafana Cloud (optional — leave blank to disable) ────────────────────────
GRAFANA_CLOUD_URL=
GRAFANA_CLOUD_USER=
GRAFANA_CLOUD_TOKEN=
GRAFANA_CLOUD_TEMPO_ENDPOINT=
GRAFANA_CLOUD_TEMPO_USER=
GRAFANA_CLOUD_TEMPO_TOKEN=
OTEL_EXPORTER_OTLP_ENDPOINT=http://alloy:4318
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
LIVEKIT_OTEL_SERVICE_NAME=livekit-server
SIP_OTEL_SERVICE_NAME=livekit-sip

# ── SSL & Proxy ───────────────────────────────────────────────────────────────
ACME_EMAIL=${acme_email}
API_DOMAIN=${api_domain}
LIVEKIT_DOMAIN=${lk_domain}
EOF

    chmod 600 "${env_file}"
    log_info ".env written to ${env_file}"
}

# ==============================================================================
# livekit-sip native binary + systemd service
# ==============================================================================

fct_install_livekit_sip() {
    log_step "livekit-sip (native binary)"

    local bin_dest="${HOME}/.local/bin/livekit-sip"
    local cfg_dir="${HOME}/.config/livekit-sip"
    local cfg_file="${cfg_dir}/config.yaml"
    local svc_file="${HOME}/.config/systemd/user/livekit-sip.service"

    # Extract binary from Docker image if not already present
    if [[ -x "${bin_dest}" ]]; then
        log_info "livekit-sip already at ${bin_dest} — skipping extract."
    else
        log_info "Pulling ${LIVEKIT_SIP_IMAGE} and extracting binary..."
        mkdir -p "${HOME}/.local/bin"

        local cid
        cid="$(docker create "${LIVEKIT_SIP_IMAGE}")"
        docker export "${cid}" | tar -x -O usr/bin/livekit-sip > "${bin_dest}"
        docker rm "${cid}" >/dev/null
        chmod +x "${bin_dest}"
        log_info "Binary installed: ${bin_dest}"
    fi

    # Write config
    mkdir -p "${cfg_dir}"
    cat > "${cfg_file}" <<EOF
log_level: debug
api_key: ${CFG_LK_API_KEY}
api_secret: ${CFG_LK_API_SECRET}
ws_url: ws://localhost:7880
redis:
  address: localhost:6379
sip_port: 5060
rtp_port: 20000-20100
use_external_ip: true
EOF
    log_info "Config written: ${cfg_file}"

    # Write systemd user service
    mkdir -p "${HOME}/.config/systemd/user"
    cat > "${svc_file}" <<EOF
[Unit]
Description=LiveKit SIP Bridge
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=%h/.local/bin/livekit-sip --config=%h/.config/livekit-sip/config.yaml
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

    systemctl --user daemon-reload
    systemctl --user enable livekit-sip
    loginctl enable-linger "${USER}" 2>/dev/null || true

    # Start or restart
    if systemctl --user is-active --quiet livekit-sip; then
        systemctl --user restart livekit-sip
        log_info "livekit-sip restarted."
    else
        systemctl --user start livekit-sip
        log_info "livekit-sip started."
    fi
}

# ==============================================================================
# Pull images + start stack
# ==============================================================================

fct_start_stack() {
    log_step "Starting Docker stack"

    cd "${INSTALL_DIR}"

    log_info "Pulling images (this may take a while on first run)..."
    docker compose pull --quiet

    log_info "Starting services..."
    docker compose up -d

    log_info "Waiting for API health..."
    local retries=30
    local i=0
    until curl -sf http://localhost:7700/health >/dev/null 2>&1; do
        i=$(( i + 1 ))
        [[ ${i} -ge ${retries} ]] && die "API did not become healthy after ${retries} attempts."
        sleep 3
    done
    log_info "API is healthy."
}

# ==============================================================================
# Register SIP trunk in LiveKit
# ==============================================================================

fct_register_sip_trunk() {
    [[ "${CFG_ENABLE_SIP}" != "true" ]] && return 0
    [[ -z "${CFG_SIP_USERNAME}" ]]      && return 0

    log_step "SIP trunk registration"

    local lk_url="http://localhost:7880"
    local lk_args=(--url "${lk_url}" --api-key "${CFG_LK_API_KEY}" --api-secret "${CFG_LK_API_SECRET}")

    # Check if the trunk already exists for this provider + username
    local existing_id=""
    existing_id="$(lk sip outbound list "${lk_args[@]}" 2>/dev/null \
        | grep -E "${CFG_SIP_USERNAME}" | awk '{print $2}' | head -1 || true)"

    if [[ -n "${existing_id}" ]]; then
        log_info "SIP trunk already registered: ${existing_id}"
        CFG_SIP_TRUNK_ID="${existing_id}"
    else
        log_info "Creating SIP trunk for ${CFG_SIP_PROVIDER}..."
        CFG_SIP_TRUNK_ID="$(lk sip outbound create \
            "${lk_args[@]}" \
            --address    "${CFG_SIP_PROVIDER}" \
            --transport  UDP \
            --auth-user  "${CFG_SIP_USERNAME}" \
            --auth-pass  "${CFG_SIP_PASSWORD}" \
            --number     "${CFG_SIP_USERNAME}" \
            2>/dev/null | grep -E '^ST_' | awk '{print $1}' | head -1 || true)"

        [[ -z "${CFG_SIP_TRUNK_ID}" ]] && log_warn "Could not capture trunk ID — set SIP_TRUNK_ID in .env manually." || true
        log_info "Trunk created: ${CFG_SIP_TRUNK_ID}"
    fi

    # Write trunk ID back into .env
    if [[ -n "${CFG_SIP_TRUNK_ID:-}" ]]; then
        sed -i "s|^SIP_TRUNK_ID=.*|SIP_TRUNK_ID=${CFG_SIP_TRUNK_ID}|" "${INSTALL_DIR}/.env"
    fi
}

# ==============================================================================
# Summary
# ==============================================================================

fct_print_summary() {
    local green; green="$(_ansi '32')"
    local red;   red="$(_ansi '31')"
    local reset; reset="$(_ansi '0')"
    local bold;  bold="$(_ansi '1')"

    _ok()   { printf '%s' "${green}✓${reset}"; }
    _fail() { printf '%s' "${red}✗${reset}"; }
    _chk()  { if curl -sf "${1}" >/dev/null 2>&1; then _ok; else _fail; fi; }
    _svc()  { if systemctl --user is-active --quiet "${1}" 2>/dev/null; then _ok; else _fail; fi; }

    printf '\n%s══════════════════════════════════════════%s\n' "${bold}" "${reset}"
    printf '%s  BotCheck setup complete%s\n' "${bold}" "${reset}"
    printf '%s══════════════════════════════════════════%s\n\n' "${bold}" "${reset}"

    printf '  %s API             %s http://localhost:7700\n'  "$(_chk http://localhost:7700/health)" "${reset}"
    printf '  %s Dashboard       %s http://localhost:3000\n'  "$(_chk http://localhost:3000)" "${reset}"
    printf '  %s livekit-sip     %s (systemd user service)\n' "$(_svc livekit-sip)" "${reset}"
    local sip_port_status
    if ss -uln | grep -q ':5060 '; then sip_port_status="$(_ok)"; else sip_port_status="$(_fail)"; fi
    printf '  %s UDP 5060        %s' "${sip_port_status}" "${reset}"
    printf ' SIP port\n'

    printf '\n  Install dir:  %s\n' "${INSTALL_DIR}"
    printf '  Admin email:  %s\n'   "${CFG_ADMIN_EMAIL}"
    printf '  Dev mode:     %s\n'   "${DEV_MODE}"
    if [[ "${CFG_ENABLE_SIP}" == "true" ]]; then
        printf '  SIP trunk:    %s via %s\n' "${CFG_SIP_TRUNK_ID:-not registered}" "${CFG_SIP_PROVIDER}"
    fi

    printf '\n  Useful commands:\n'
    printf '    docker compose -f %s/docker-compose.yml logs -f\n' "${INSTALL_DIR}"
    printf '    journalctl --user -u livekit-sip -f\n'
    printf '    systemctl --user restart livekit-sip\n\n'
}

# ==============================================================================
# Main
# ==============================================================================

main() {
    fct_parse_args "$@"

    TMP_DIR="$(mktemp -d "/tmp/${SCRIPT_NAME}.XXXXXXXX")"

    printf '\n%s BotCheck Setup v%s %s\n\n' \
        "$(_ansi '1;36')══" "${SCRIPT_VERSION}" "══$(_ansi '0')"

    [[ "${DEV_MODE}" == "true" ]] && log_info "Running in DEV mode."

    fct_detect_os
    fct_install_prerequisites
    fct_install_docker
    fct_install_lk_cli
    fct_clone_or_update_repo
    fct_load_existing_env
    fct_prompt_configuration
    fct_write_env
    fct_install_livekit_sip
    fct_start_stack
    fct_register_sip_trunk
    fct_print_summary
}

main "$@"
