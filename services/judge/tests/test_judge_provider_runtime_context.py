from botcheck_judge.provider_runtime_context import (
    RuntimeSettingsOverlay,
    build_settings_overrides,
)


def test_build_settings_overrides_maps_provider_secret_fields() -> None:
    overrides = build_settings_overrides(
        {
            "feature_flags": {
                "feature_tts_provider_openai_enabled": False,
            },
            "tts": {
                "vendor": "openai",
                "secret_fields": {"api_key": "stored-openai-key"},
            },
            "providers": [
                {
                    "vendor": "anthropic",
                    "secret_fields": {"api_key": "stored-anthropic-key"},
                }
            ],
        }
    )

    assert overrides["feature_tts_provider_openai_enabled"] is False
    assert overrides["openai_api_key"] == "stored-openai-key"
    assert overrides["anthropic_api_key"] == "stored-anthropic-key"


def test_runtime_settings_overlay_masks_base_provider_secrets_without_override() -> None:
    base_settings = type(
        "SettingsStub",
        (),
        {
            "anthropic_api_key": "env-anthropic-key",
            "openai_api_key": "env-openai-key",
            "feature_tts_provider_openai_enabled": True,
        },
    )()
    overlay = RuntimeSettingsOverlay(
        base_settings=base_settings,
        overrides={},
    )

    assert overlay.anthropic_api_key == ""
    assert overlay.openai_api_key == ""
    assert overlay.feature_tts_provider_openai_enabled is True


def test_post_provider_circuit_state_accepts_positional_args() -> None:
    """_post_provider_circuit_state must not use keyword-only parameters.

    Regression: the function previously declared `async def fn(*, provider, state,
    observed_at)` — the `*,` made all params keyword-only — but was passed as a
    `Callable[[str, str, datetime], ...]` callback and called with positional args,
    raising TypeError on every circuit state transition and tripping the circuit
    breaker open so all subsequent TTS synthesis calls were rejected.

    Uses AST parsing to avoid importing the module (which requires S3 env vars).
    """
    import ast
    from pathlib import Path

    source_path = (
        Path(__file__).parent.parent
        / "botcheck_judge"
        / "workers"
        / "cache_worker.py"
    )
    source = source_path.read_text()
    tree = ast.parse(source)

    # Find _post_provider_circuit_state async def
    fn_node = None
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
            and node.name == "_post_provider_circuit_state"
        ):
            fn_node = node
            break

    assert fn_node is not None, (
        "_post_provider_circuit_state not found in cache_worker.py — "
        "was it renamed or deleted?"
    )

    # kwonlyargs is non-empty when `*` or `*args` appears before regular params
    keyword_only = [arg.arg for arg in fn_node.args.kwonlyargs]
    assert not keyword_only, (
        "_post_provider_circuit_state has keyword-only parameters — it is passed "
        "as a positional callback and must accept positional args. "
        "Remove the bare `*,` from its signature. "
        "Keyword-only params: " + ", ".join(keyword_only)
    )
