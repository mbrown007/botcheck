from __future__ import annotations

from botcheck_scenarios import (
    AIRunDispatchContext,
    HarnessPromptBlock,
    PromptContent,
    ScenarioDefinition,
)

AI_RUNTIME_TAG = "__ai_runtime__"


def _metadata_text(
    metadata: dict[str, object],
    key: str,
    *,
    default: str = "",
) -> str:
    raw = metadata.get(key, default)
    if isinstance(raw, str):
        return raw.strip()
    if raw is None:
        return default
    return str(raw).strip()


def materialize_runtime_scenario(
    *,
    scenario: ScenarioDefinition,
    metadata: dict[str, object],
) -> ScenarioDefinition:
    """Build the execution scenario for the current run kind.

    Graph runs execute the scenario as-authored.
    AI runs are dataset-record driven and synthesize a runtime harness turn from
    the dispatch context captured in room metadata.
    """
    # scenario_kind is a RunRoomMetadata field (not on AIRunDispatchContext), so we
    # read it via the bespoke helper before constructing the typed dispatch context.
    scenario_kind = _metadata_text(metadata, "scenario_kind", default="graph").lower()
    if scenario_kind != "ai":
        return scenario

    dispatch_context = AIRunDispatchContext.model_validate(metadata)
    dataset_input = dispatch_context.ai_dataset_input or ""
    if not dataset_input:
        raise ValueError("AI scenario dispatch context missing required 'ai_dataset_input'.")

    ai_turn = HarnessPromptBlock(
        id="ai_record_input",
        content=PromptContent(text=dataset_input),
        listen=True,
    )
    tags = list(dict.fromkeys([*scenario.tags, AI_RUNTIME_TAG]))
    return scenario.model_copy(update={"turns": [ai_turn], "tags": tags}, deep=True)
