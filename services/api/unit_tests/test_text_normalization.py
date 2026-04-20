from __future__ import annotations

import pytest

from pydantic import ValidationError

from botcheck_api.packs.destinations import BotDestinationUpsert
from botcheck_api.providers.schemas import AdminProviderCreateRequest, AdminProviderQuotaPolicyWriteRequest
from botcheck_api.runs.runs import RunHeartbeatRequest
from botcheck_api.text_normalization import strip_lower_or_none, strip_nonempty, strip_or_none


def test_strip_or_none_trims_and_collapses_blank() -> None:
    assert strip_or_none("  hello  ") == "hello"
    assert strip_or_none("   ") is None
    assert strip_or_none("") is None
    assert strip_or_none(None) is None


def test_strip_nonempty_trims_and_rejects_blank() -> None:
    assert strip_nonempty("hello") == "hello"
    assert strip_nonempty("  hello  ") == "hello"

    with pytest.raises(ValueError, match="value must not be blank"):
        strip_nonempty("   ")

    with pytest.raises(ValueError, match="value must not be blank"):
        strip_nonempty("")


def test_strip_nonempty_uses_custom_error_message() -> None:
    with pytest.raises(ValueError, match="name is required"):
        strip_nonempty("   ", error_message="name is required")


def test_strip_lower_or_none_trims_lowercases_and_collapses_blank() -> None:
    assert strip_lower_or_none("  HeLLo  ") == "hello"
    assert strip_lower_or_none("   ") is None
    assert strip_lower_or_none("") is None
    assert strip_lower_or_none(None) is None


def test_destination_schema_reuses_shared_trim_helpers() -> None:
    payload = BotDestinationUpsert.model_validate(
        {
            "name": "  Direct HTTP Bot  ",
            "protocol": "http",
            "endpoint": "  https://bot.internal/chat  ",
            "capacity_scope": "  team-a  ",
        }
    )

    assert payload.name == "Direct HTTP Bot"
    assert payload.endpoint == "https://bot.internal/chat"
    assert payload.capacity_scope == "team-a"

    # Optional field with whitespace-only value collapses to None.
    blank_scope = BotDestinationUpsert.model_validate(
        {"name": "Bot", "protocol": "mock", "capacity_scope": "   "}
    )
    assert blank_scope.capacity_scope is None

    # Required field with whitespace-only value raises.
    with pytest.raises(ValidationError):
        BotDestinationUpsert.model_validate({"name": "   ", "protocol": "mock"})


def test_provider_schema_reuses_shared_trim_helpers() -> None:
    payload = AdminProviderCreateRequest.model_validate(
        {
            "capability": "  TTS  ",
            "vendor": "  OpenAI  ",
            "model": "  gpt-4o-mini-tts  ",
            "api_key": "  secret  ",
        }
    )

    assert payload.capability == "tts"
    assert payload.vendor == "openai"
    assert payload.model == "gpt-4o-mini-tts"
    assert payload.api_key == "secret"

    # Blank capability raises with a specific "must not be blank" message (not the
    # allowlist message) — the strip_nonempty guard fires before the allowlist check.
    with pytest.raises(ValidationError, match="capability must not be blank"):
        AdminProviderCreateRequest.model_validate(
            {"capability": "   ", "vendor": "openai", "model": "m", "api_key": "k"}
        )

    # label is optional — whitespace-only collapses to None.
    no_label = AdminProviderCreateRequest.model_validate(
        {"capability": "llm", "vendor": "openai", "model": "m", "api_key": "k", "label": "   "}
    )
    assert no_label.label is None


def test_provider_quota_policy_schema_normalizes_metric() -> None:
    policy = AdminProviderQuotaPolicyWriteRequest.model_validate(
        {
            "tenant_id": "t1",
            "metric": "  input_tokens  ",
            "limit_per_day": 1000,
        }
    )
    assert policy.metric == "input_tokens"

    with pytest.raises(ValidationError, match="metric must not be blank"):
        AdminProviderQuotaPolicyWriteRequest.model_validate(
            {"tenant_id": "t1", "metric": "   ", "limit_per_day": 1000}
        )


def test_run_heartbeat_schema_reuses_lowercase_trim_helper() -> None:
    heartbeat = RunHeartbeatRequest.model_validate(
        {"sent_at": "2026-03-27T12:00:00Z", "seq": 1, "listener_state": "  Awaiting_Bot  "}
    )
    assert heartbeat.listener_state == "awaiting_bot"

    blank = RunHeartbeatRequest.model_validate(
        {"sent_at": "2026-03-27T12:00:00Z", "seq": 1, "listener_state": "   "}
    )
    assert blank.listener_state is None

    # Max-length boundary: 64 chars passes, 65 chars raises.
    at_limit = RunHeartbeatRequest.model_validate(
        {"sent_at": "2026-03-27T12:00:00Z", "seq": 1, "listener_state": "a" * 64}
    )
    assert at_limit.listener_state == "a" * 64

    with pytest.raises(ValidationError, match="listener_state must be"):
        RunHeartbeatRequest.model_validate(
            {"sent_at": "2026-03-27T12:00:00Z", "seq": 1, "listener_state": "a" * 65}
        )

    # Whitespace does not count toward the 64-character limit.
    padded = RunHeartbeatRequest.model_validate(
        {"sent_at": "2026-03-27T12:00:00Z", "seq": 1, "listener_state": "  " + "a" * 64 + "  "}
    )
    assert padded.listener_state == "a" * 64
