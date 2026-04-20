from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379"
    botcheck_api_url: str = "http://api:8000"
    judge_secret: str = "dev-judge-secret"
    scheduler_secret: str = "dev-scheduler-secret"

    anthropic_api_key: str | None = None
    judge_model: str = "claude-sonnet-4-6"
    """Model used for semantic scoring. Use claude-opus-4-6 for adversarial scenarios."""
    multi_sample_judge: bool = False
    """When enabled, adversarial scenarios run N judge samples and aggregate with min score."""
    multi_sample_judge_n: int = Field(default=3, ge=1, le=10)
    """Number of judge samples for adversarial multi-sample mode (1–10)."""

    judge_version: str = "0.1.0"

    # Phase 10: AI Scenario Generator
    scenario_generator_model: str = "claude-sonnet-4-5-20251001"

    # TTS cache warm worker settings (Phase 7).
    tts_cache_enabled: bool = True
    tts_cache_openai_model: str = "gpt-4o-mini-tts"
    tts_cache_elevenlabs_model: str = "eleven_flash_v2_5"
    tts_cache_elevenlabs_output_format: str = "pcm_24000"
    tts_cache_request_timeout_s: float = Field(default=30.0, ge=1.0, le=120.0)
    tts_cache_turn_max_attempts: int = Field(default=2, ge=1, le=5)
    tts_cache_turn_retry_backoff_s: float = Field(default=1.0, ge=0.0, le=30.0)
    tts_cache_circuit_failure_threshold: int = Field(default=5, ge=1, le=100)
    tts_cache_circuit_recovery_s: float = Field(default=30.0, ge=1.0, le=3600.0)
    feature_tts_provider_openai_enabled: bool = True
    feature_tts_provider_elevenlabs_enabled: bool = False
    tts_cache_max_jobs: int = Field(default=3, ge=1, le=50)
    tts_cache_gc_enabled: bool = True
    tts_cache_max_age_days: int = Field(default=30, ge=1, le=3650)
    tts_cache_tenant_max_gb: float = Field(default=0.0, ge=0.0, le=10000.0)
    openai_api_key: str | None = None
    elevenlabs_api_key: str | None = None

    s3_endpoint_url: str | None = None
    s3_access_key: str
    s3_secret_key: str
    s3_region: str = "us-east-1"
    s3_bucket_prefix: str = "botcheck-artifacts"

    metrics_enabled: bool = True
    metrics_host: str = "0.0.0.0"
    metrics_port: int = 9101

    retention_sweep_enabled: bool = True
    retention_sweep_dry_run: bool = False
    retention_sweep_limit: int = Field(default=500, ge=1, le=5000)
    run_reaper_enabled: bool = True
    run_reaper_limit: int = Field(default=200, ge=1, le=5000)
    run_reaper_grace_s: float = Field(default=60.0, ge=0.0, le=3600.0)
    schedule_tick_enabled: bool = True
    schedule_tick_limit: int = Field(default=50, ge=1, le=500)

    # Phase 17: AI scenarios/persona agents (feature-flagged rollout).
    feature_ai_scenarios_enabled: bool = False


settings = Settings()  # type: ignore[call-arg]
