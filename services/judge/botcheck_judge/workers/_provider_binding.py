"""Shared provider binding helpers used by both judge_worker and generator_task."""
from __future__ import annotations


def binding_for_capability(
    runtime_context: dict[str, object] | None,
    *,
    capability: str,
) -> dict[str, object] | None:
    """Return the first provider binding matching *capability*, or None."""
    if not isinstance(runtime_context, dict):
        return None
    providers = runtime_context.get("providers")
    if not isinstance(providers, list):
        return None
    for provider in providers:
        if not isinstance(provider, dict):
            continue
        if str(provider.get("capability") or "").strip().lower() == capability:
            return provider
    return None
