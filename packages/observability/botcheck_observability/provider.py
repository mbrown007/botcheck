from __future__ import annotations

from .helpers import counter

PROVIDER_API_CALLS_TOTAL = counter(
    "botcheck_provider_api_calls_total",
    "Total API calls to external providers.",
    ["provider", "service", "model", "outcome"],
)

LLM_TOKENS_TOTAL = counter(
    "botcheck_llm_tokens_total",
    "Total LLM tokens consumed.",
    ["provider", "model", "token_type"],
)

TTS_CHARACTERS_TOTAL = counter(
    "botcheck_tts_characters_total",
    "Total characters synthesized by TTS.",
    ["provider", "model", "scenario_kind"],
)

STT_SECONDS_TOTAL = counter(
    "botcheck_stt_seconds_total",
    "Total audio seconds processed by STT.",
    ["provider", "model", "scenario_kind"],
)

TELEPHONY_MINUTES_TOTAL = counter(
    "botcheck_telephony_minutes_total",
    "Total telephony minutes (SIP/PSTN).",
    ["provider", "direction"],
)

TTS_PREVIEW_REQUESTS_TOTAL = counter(
    "botcheck_tts_preview_requests_total",
    "Scenario TTS preview requests by outcome.",
    ["outcome"],
)
