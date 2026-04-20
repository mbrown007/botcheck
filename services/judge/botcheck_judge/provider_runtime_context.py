from __future__ import annotations

from typing import Any

_PROVIDER_SECRET_DEFAULTS: dict[str, object] = {
    "anthropic_api_key": "",
    "openai_api_key": "",
    "elevenlabs_api_key": "",
}


class RuntimeSettingsOverlay:
    def __init__(self, *, base_settings: Any, overrides: dict[str, object]) -> None:
        self._base_settings = base_settings
        self._overrides = dict(overrides)

    def __getattr__(self, name: str) -> object:
        overrides = object.__getattribute__(self, "_overrides")
        if name in overrides:
            return overrides[name]
        if name in _PROVIDER_SECRET_DEFAULTS:
            return _PROVIDER_SECRET_DEFAULTS[name]
        base = object.__getattribute__(self, "_base_settings")
        return getattr(base, name)


def build_settings_overrides(runtime_context: dict[str, object] | None) -> dict[str, object]:
    if not isinstance(runtime_context, dict):
        return {}

    overrides: dict[str, object] = {}
    feature_flags = runtime_context.get("feature_flags")
    if isinstance(feature_flags, dict):
        for key, value in feature_flags.items():
            overrides[str(key)] = bool(value)

    tts = runtime_context.get("tts")
    if isinstance(tts, dict):
        secret_fields = tts.get("secret_fields")
        vendor = str(tts.get("vendor") or "").strip().lower()
        if isinstance(secret_fields, dict):
            api_key = str(secret_fields.get("api_key") or "").strip()
            if vendor == "openai" and api_key:
                overrides["openai_api_key"] = api_key
            if vendor == "elevenlabs" and api_key:
                overrides["elevenlabs_api_key"] = api_key

    providers = runtime_context.get("providers")
    if isinstance(providers, list):
        for provider in providers:
            if not isinstance(provider, dict):
                continue
            secret_fields = provider.get("secret_fields")
            vendor = str(provider.get("vendor") or "").strip().lower()
            if not isinstance(secret_fields, dict):
                continue
            api_key = str(secret_fields.get("api_key") or "").strip()
            if vendor == "anthropic" and api_key:
                overrides["anthropic_api_key"] = api_key
            if vendor == "openai" and api_key:
                overrides["openai_api_key"] = api_key

    return overrides
