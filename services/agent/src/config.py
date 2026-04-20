from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    log_level: str = "INFO"
    log_json: bool = True

    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str

    botcheck_api_url: str = "http://localhost:7700"
    harness_secret: str = "dev-harness-secret"

    openai_api_key: str
    elevenlabs_api_key: str = ""
    deepgram_api_key: str
    azure_speech_key: str = ""
    azure_speech_region: str = ""
    azure_speech_endpoint: str = ""

    # TTS defaults (overridable per scenario)
    default_tts_voice: str = "nova"
    default_language: str = "en-US"

    # Phase 7: harness read-through TTS cache.
    tenant_id: str = "default"
    tts_cache_enabled: bool = False
    tts_cache_pcm_format_version: str = "v1"
    tts_cache_prefetch_enabled: bool = True
    tts_cache_prefetch_max_concurrency: int = Field(default=4, ge=1, le=32)
    s3_endpoint_url: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket_prefix: str = "botcheck-artifacts"

    metrics_enabled: bool = True
    metrics_host: str = "0.0.0.0"
    metrics_port: int = 9102

    # Greedy final ACK hardening: persist callback failures for replay.
    final_ack_recovery_enabled: bool = True
    final_ack_recovery_log_path: str = "/tmp/botcheck-agent-final-ack-recovery.jsonl"

    # Optional bot-leg call recording upload.
    recording_upload_enabled: bool = True
    recording_upload_timeout_s: float = 20.0
    recording_tmp_dir: str = "/tmp/botcheck-recordings"

    # Graph execution engine (branching flows). Always on; flag kept for emergency rollback.
    enable_branching_graph: bool = True
    max_total_turns_hard_cap: int = 50
    branch_classifier_model: str = "claude-3-5-haiku-latest"
    branch_classifier_timeout_s: float = 1.5

    # External provider circuit breaker (live TTS path).
    # Graph scenario cache-miss path: tight deadline, fail fast.
    tts_live_synthesis_timeout_s: float = Field(default=10.0, ge=1.0, le=60.0)
    # AI scenario path: TTS is always live (no cache), so allow more headroom.
    tts_ai_scenario_synthesis_timeout_s: float = Field(default=30.0, ge=1.0, le=120.0)
    tts_live_openai_model: str = "gpt-4o-mini-tts"
    tts_live_elevenlabs_model: str = "eleven_flash_v2_5"
    tts_live_elevenlabs_output_format: str = "pcm_24000"
    tts_live_circuit_failure_threshold: int = Field(default=3, ge=1)
    tts_live_circuit_recovery_s: float = Field(default=30.0, ge=1.0)
    feature_tts_provider_openai_enabled: bool = True
    feature_tts_provider_elevenlabs_enabled: bool = False
    feature_stt_provider_deepgram_enabled: bool = True
    feature_stt_provider_azure_enabled: bool = False

    # Phase 6 hardening: run heartbeat callbacks for liveness tracking.
    run_heartbeat_enabled: bool = True
    run_heartbeat_interval_s: float = 30.0
    run_heartbeat_jitter_s: float = 5.0
    service_heartbeat_enabled: bool = True
    service_heartbeat_interval_s: float = 30.0
    service_heartbeat_jitter_s: float = 5.0

    # Phase 17: AI scenarios/persona agents (feature-flagged rollout).
    feature_ai_scenarios_enabled: bool = False
    ai_voice_latency_profile_enabled: bool = False
    ai_voice_latency_profile_stt_endpointing_ms: int = Field(default=1200, ge=0, le=10000)
    ai_voice_latency_profile_transcript_merge_window_s: float = Field(
        default=0.75,
        gt=0.0,
        le=10.0,
    )
    ai_voice_preview_events_enabled: bool = False
    ai_voice_speculative_planning_enabled: bool = False
    ai_voice_speculative_min_preview_chars: int = Field(default=24, ge=1, le=500)
    ai_voice_fast_ack_enabled: bool = False
    ai_voice_fast_ack_trigger_s: float = Field(default=0.6, gt=0.0, le=5.0)
    ai_voice_early_playback_enabled: bool = False
    ai_caller_use_llm: bool = True
    ai_caller_model: str = "gpt-4o-mini"
    ai_caller_timeout_s: float = 4.0
    ai_caller_max_context_turns: int = 8
    ai_caller_api_base_url: str = "https://api.openai.com/v1"
    playground_mock_agent_model: str = "gpt-4o-mini"
    playground_mock_agent_timeout_s: float = 6.0
    playground_mock_agent_api_base_url: str = "https://api.openai.com/v1"
    ai_caller_circuit_failure_threshold: int = Field(default=5, ge=1)
    ai_caller_circuit_recovery_s: float = Field(default=30.0, ge=1.0)


settings = Settings()  # type: ignore[call-arg]
