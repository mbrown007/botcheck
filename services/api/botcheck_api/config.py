from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from zoneinfo import ZoneInfo
from cryptography.fernet import Fernet


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"
    log_json: bool = True
    secret_key: str = "dev-secret-change-in-production"
    auth_algorithm: str = "HS256"
    auth_issuer: str = "botcheck-local-auth"

    # Default single-tenant instance settings (v1 deployment model)
    tenant_id: str = "default"
    tenant_name: str = "Default Tenant"
    tenant_plan: str = "soft"
    default_retention_profile: str = "standard"
    instance_timezone: str = "UTC"
    redaction_enabled: bool = True
    shared_instance_mode: bool = False
    tenant_switcher_allowed_roles: list[str] = ["admin"]

    # Dev convenience token for UI/API calls before OIDC is wired.
    # In production this should be disabled and replaced by real JWTs.
    dev_user_token: str = "dev-admin-token"

    # Phase 6 local auth (interim provider before OIDC integration)
    local_auth_enabled: bool = True
    local_auth_email: str = "admin@botcheck.local"
    local_auth_password: str = "botcheck-dev-password"
    local_auth_password_hash: str = ""
    local_auth_token_ttl_s: int = 15 * 60
    local_auth_refresh_token_ttl_s: int = 8 * 60 * 60
    local_auth_rate_limit_attempts: int = 10
    local_auth_rate_limit_window_s: int = 60
    local_auth_lockout_failed_attempts: int = 5
    local_auth_lockout_duration_s: int = 15 * 60
    auth_totp_challenge_ttl_s: int = 5 * 60
    auth_totp_step_s: int = 30
    auth_totp_window: int = 1
    auth_totp_replay_ttl_s: int = 2 * 60
    auth_security_redis_enabled: bool = True
    auth_security_redis_prefix: str = "botcheck:authsec"
    auth_security_redis_timeout_s: float = 0.2
    auth_security_redis_failure_backoff_s: float = 5.0
    auth_totp_encryption_key: str = ""
    users_bootstrap_enabled: bool = True
    users_bootstrap_path: str = "botcheck_api/users.yaml"

    # Service-to-service callback secrets (harness/judge -> API)
    harness_secret: str = "dev-harness-secret"
    judge_secret: str = "dev-judge-secret"
    scheduler_secret: str = "dev-scheduler-secret"
    metrics_scrape_token: str = "botcheck-dev-metrics-token"

    # Database — optional in dev (in-memory store is used when None)
    database_url: str | None = None

    # Redis
    redis_url: str = "redis://localhost:6379"

    # LiveKit
    livekit_url: str = "ws://localhost:7880"
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"
    enable_outbound_sip: bool = False

    # Outbound SIP trunk + destination controls
    sip_secret_provider: str = "env"  # env|vault|aws_secrets_manager
    sip_secret_ref: str | None = None
    sip_secret_cache_ttl_s: int = 60
    allow_env_sip_secrets_in_production: bool = False
    sip_secret_region: str = "us-east-1"
    sip_secret_timeout_s: float = 5.0
    vault_addr: str | None = None
    vault_token: str | None = None
    vault_namespace: str | None = None
    vault_kv_version: int = 2
    sip_trunk_id: str = ""
    sip_auth_username: str = ""
    sip_auth_password: str = ""
    sip_destination_allowlist: list[str] = []
    max_concurrent_outbound_calls: int = 5
    sip_dispatch_slot_ttl_s: int = 900
    schedule_dispatch_backoff_s: int = 15
    schedule_dispatch_backoff_jitter_s: int = 5
    schedule_dispatch_max_attempts: int = 5

    # OpenAI (judge scoring)
    openai_api_key: str = ""
    elevenlabs_api_key: str = ""
    deepgram_api_key: str = ""
    azure_speech_key: str = ""
    azure_speech_region: str = ""
    azure_speech_endpoint: str = ""

    # Phase 7: global TTS cache capability toggle for scenario cache endpoints.
    tts_cache_enabled: bool = True
    tts_cache_pcm_format_version: str = "v1"
    tts_preview_rate_limit_attempts: int = 30
    tts_preview_rate_limit_window_s: int = 60
    tts_preview_openai_model: str = "gpt-4o-mini-tts"
    tts_preview_elevenlabs_model: str = "eleven_flash_v2_5"
    tts_preview_elevenlabs_output_format: str = "pcm_24000"
    tts_preview_request_timeout_s: float = 20.0
    tts_preview_circuit_failure_threshold: int = 5
    tts_preview_circuit_recovery_s: float = 30.0
    feature_tts_provider_openai_enabled: bool = True
    feature_tts_provider_elevenlabs_enabled: bool = False
    feature_stt_provider_deepgram_enabled: bool = True
    feature_stt_provider_azure_enabled: bool = False
    provider_circuit_snapshot_ttl_s: int = 180
    provider_circuit_snapshot_stale_s: float = 120.0
    run_dispatch_require_harness_healthy: bool = False

    # Phase 6 hardening: run heartbeat reconciliation.
    run_heartbeat_enabled: bool = True
    run_heartbeat_stale_s: float = 120.0
    run_pending_stale_s: float = 120.0

    # Object storage — optional in dev
    s3_endpoint_url: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket_prefix: str = "botcheck-artifacts"
    recording_max_upload_bytes: int = 50 * 1024 * 1024

    # Judge service (used when running judge as a separate service via ARQ)
    botcheck_judge_url: str = "http://judge:8001"
    anthropic_api_key: str = ""
    grai_eval_judge_model: str = "claude-sonnet-4-6"
    eval_concurrency_limit: int = 20
    eval_requests_per_second: float = 0.0
    eval_job_timeout_s: int = 7200

    # Phase 10: AI Scenario Generator
    scenario_generator_rate_limit_per_hour: int = 10
    scenario_generator_model: str = "claude-sonnet-4-5-20251001"

    # Phase 9: Scenario packs (feature-flagged until rollout).
    feature_packs_enabled: bool = False
    # Phase 11: Destination registry (feature-flagged until rollout).
    feature_destinations_enabled: bool = False
    # Phase 17: AI scenarios and persona agents (feature-flagged until rollout).
    feature_ai_scenarios_enabled: bool = False

    # Dev: auto-dispatch the mock bot alongside the harness so runs complete
    # without a real SIP bot. Disable in production/staging.
    enable_mock_bot: bool = False

    @field_validator("sip_destination_allowlist", mode="before")
    @classmethod
    def _parse_allowlist(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            # Support comma-separated env var format in addition to JSON arrays.
            return [part.strip().lower() for part in value.split(",") if part.strip()]
        if isinstance(value, list):
            return [str(part).strip().lower() for part in value if str(part).strip()]
        return value

    @field_validator("tenant_switcher_allowed_roles", mode="before")
    @classmethod
    def _parse_tenant_switcher_allowed_roles(cls, value):
        if value is None:
            return ["admin"]
        if isinstance(value, str):
            return [part.strip().lower() for part in value.split(",") if part.strip()]
        if isinstance(value, list):
            return [str(part).strip().lower() for part in value if str(part).strip()]
        return value

    @field_validator("instance_timezone")
    @classmethod
    def _validate_instance_timezone(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate:
            raise ValueError("instance_timezone must not be empty")
        try:
            ZoneInfo(candidate)
        except Exception as exc:
            raise ValueError(f"invalid timezone: {candidate}") from exc
        return candidate

    @field_validator("sip_secret_cache_ttl_s")
    @classmethod
    def _validate_secret_cache_ttl(cls, value: int) -> int:
        if value < 0:
            raise ValueError("sip_secret_cache_ttl_s must be >= 0")
        return value

    @field_validator("vault_kv_version")
    @classmethod
    def _validate_vault_kv_version(cls, value: int) -> int:
        if value not in {1, 2}:
            raise ValueError("vault_kv_version must be 1 or 2")
        return value

    @field_validator("default_retention_profile")
    @classmethod
    def _validate_default_retention_profile(cls, value: str) -> str:
        candidate = value.strip().lower()
        allowed = {"ephemeral", "standard", "compliance", "no_audio"}
        if candidate not in allowed:
            raise ValueError(
                f"default_retention_profile must be one of {sorted(allowed)}"
            )
        return candidate

    @field_validator("recording_max_upload_bytes")
    @classmethod
    def _validate_recording_max_upload_bytes(cls, value: int) -> int:
        if value < 1024:
            raise ValueError("recording_max_upload_bytes must be >= 1024")
        return value

    @field_validator("tts_preview_rate_limit_attempts")
    @classmethod
    def _validate_tts_preview_rate_limit_attempts(cls, value: int) -> int:
        if value < 0:
            raise ValueError("tts_preview_rate_limit_attempts must be >= 0")
        return value

    @field_validator("tts_preview_rate_limit_window_s")
    @classmethod
    def _validate_tts_preview_rate_limit_window_s(cls, value: int) -> int:
        if value < 1:
            raise ValueError("tts_preview_rate_limit_window_s must be >= 1")
        return value

    @field_validator("tts_preview_request_timeout_s")
    @classmethod
    def _validate_tts_preview_request_timeout_s(cls, value: float) -> float:
        if value < 1.0:
            raise ValueError("tts_preview_request_timeout_s must be >= 1.0")
        return value

    @field_validator("eval_concurrency_limit")
    @classmethod
    def _validate_eval_concurrency_limit(cls, value: int) -> int:
        if value < 1 or value > 100:
            raise ValueError("eval_concurrency_limit must be between 1 and 100")
        return value

    @field_validator("eval_requests_per_second")
    @classmethod
    def _validate_eval_requests_per_second(cls, value: float) -> float:
        if value < 0:
            raise ValueError("eval_requests_per_second must be >= 0")
        return value

    @field_validator("eval_job_timeout_s")
    @classmethod
    def _validate_eval_job_timeout_s(cls, value: int) -> int:
        if value < 60:
            raise ValueError("eval_job_timeout_s must be >= 60")
        return value

    @field_validator("tts_preview_circuit_failure_threshold")
    @classmethod
    def _validate_tts_preview_circuit_failure_threshold(cls, value: int) -> int:
        if value < 1:
            raise ValueError("tts_preview_circuit_failure_threshold must be >= 1")
        return value

    @field_validator("tts_preview_circuit_recovery_s")
    @classmethod
    def _validate_tts_preview_circuit_recovery_s(cls, value: float) -> float:
        if value < 1.0:
            raise ValueError("tts_preview_circuit_recovery_s must be >= 1.0")
        return value

    @field_validator("provider_circuit_snapshot_ttl_s")
    @classmethod
    def _validate_provider_circuit_snapshot_ttl_s(cls, value: int) -> int:
        if value < 1:
            raise ValueError("provider_circuit_snapshot_ttl_s must be >= 1")
        return value

    @field_validator("provider_circuit_snapshot_stale_s")
    @classmethod
    def _validate_provider_circuit_snapshot_stale_s(cls, value: float) -> float:
        if value < 1.0:
            raise ValueError("provider_circuit_snapshot_stale_s must be >= 1.0")
        return value

    @field_validator("run_heartbeat_stale_s")
    @classmethod
    def _validate_run_heartbeat_stale_s(cls, value: float) -> float:
        if value < 1.0:
            raise ValueError("run_heartbeat_stale_s must be >= 1.0")
        return value

    @field_validator("local_auth_email")
    @classmethod
    def _validate_local_auth_email(cls, value: str) -> str:
        candidate = value.strip().lower()
        if not candidate or "@" not in candidate:
            raise ValueError("local_auth_email must be a valid email-like value")
        return candidate

    @field_validator("local_auth_token_ttl_s")
    @classmethod
    def _validate_local_auth_token_ttl_s(cls, value: int) -> int:
        if value < 60:
            raise ValueError("local_auth_token_ttl_s must be >= 60")
        return value

    @field_validator("local_auth_refresh_token_ttl_s")
    @classmethod
    def _validate_local_auth_refresh_token_ttl_s(cls, value: int) -> int:
        if value < 300:
            raise ValueError("local_auth_refresh_token_ttl_s must be >= 300")
        return value

    @field_validator("local_auth_rate_limit_attempts")
    @classmethod
    def _validate_local_auth_rate_limit_attempts(cls, value: int) -> int:
        if value < 0:
            raise ValueError("local_auth_rate_limit_attempts must be >= 0")
        return value

    @field_validator("local_auth_rate_limit_window_s")
    @classmethod
    def _validate_local_auth_rate_limit_window_s(cls, value: int) -> int:
        if value < 1:
            raise ValueError("local_auth_rate_limit_window_s must be >= 1")
        return value

    @field_validator("local_auth_lockout_failed_attempts")
    @classmethod
    def _validate_local_auth_lockout_failed_attempts(cls, value: int) -> int:
        if value < 0:
            raise ValueError("local_auth_lockout_failed_attempts must be >= 0")
        return value

    @field_validator("local_auth_lockout_duration_s")
    @classmethod
    def _validate_local_auth_lockout_duration_s(cls, value: int) -> int:
        if value < 1:
            raise ValueError("local_auth_lockout_duration_s must be >= 1")
        return value

    @field_validator("auth_totp_challenge_ttl_s")
    @classmethod
    def _validate_auth_totp_challenge_ttl_s(cls, value: int) -> int:
        if value < 60:
            raise ValueError("auth_totp_challenge_ttl_s must be >= 60")
        return value

    @field_validator("auth_totp_step_s")
    @classmethod
    def _validate_auth_totp_step_s(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("auth_totp_step_s must be > 0")
        return value

    @field_validator("auth_totp_window")
    @classmethod
    def _validate_auth_totp_window(cls, value: int) -> int:
        if value < 0 or value > 5:
            raise ValueError("auth_totp_window must be between 0 and 5")
        return value

    @field_validator("auth_totp_replay_ttl_s")
    @classmethod
    def _validate_auth_totp_replay_ttl_s(cls, value: int) -> int:
        if value < 30:
            raise ValueError("auth_totp_replay_ttl_s must be >= 30")
        return value

    @field_validator("metrics_scrape_token")
    @classmethod
    def _validate_metrics_scrape_token(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("metrics_scrape_token must not be empty")
        return value

    @field_validator("auth_security_redis_prefix")
    @classmethod
    def _validate_auth_security_redis_prefix(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate:
            raise ValueError("auth_security_redis_prefix must not be empty")
        return candidate

    @field_validator("auth_security_redis_timeout_s")
    @classmethod
    def _validate_auth_security_redis_timeout_s(cls, value: float) -> float:
        if value <= 0.0:
            raise ValueError("auth_security_redis_timeout_s must be > 0")
        return value

    @field_validator("auth_security_redis_failure_backoff_s")
    @classmethod
    def _validate_auth_security_redis_failure_backoff_s(cls, value: float) -> float:
        if value < 0.0:
            raise ValueError("auth_security_redis_failure_backoff_s must be >= 0")
        return value

    @field_validator("auth_totp_encryption_key")
    @classmethod
    def _validate_auth_totp_encryption_key(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate:
            return candidate
        try:
            Fernet(candidate.encode())
        except Exception as exc:
            raise ValueError("auth_totp_encryption_key must be a valid Fernet key") from exc
        return candidate

    @model_validator(mode="after")
    def _validate_production_security(self):
        if not self.is_production:
            return self

        if self.secret_key == "dev-secret-change-in-production":
            raise ValueError("secret_key must be changed in production")

        if self.dev_user_token.strip():
            raise ValueError("dev_user_token must be empty in production")

        if self.local_auth_password_hash.strip() and self.local_auth_password.strip():
            raise ValueError(
                "local_auth_password must be empty when local_auth_password_hash is set in production"
            )

        if self.local_auth_enabled and not self.auth_totp_encryption_key.strip():
            raise ValueError("auth_totp_encryption_key must be set in production when local_auth_enabled=true")

        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


settings = Settings()  # type: ignore[call-arg]
