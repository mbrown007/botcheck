"""
judge_conversation() — standalone entry point for the judge logic.

No ARQ, no HTTP, no infrastructure dependencies. Takes everything it needs
as arguments, returns a RunReport. Can be called from:
  - the ARQ worker (services/judge/src/workers/judge_worker.py)
  - the CLI / PoC scripts
  - unit tests
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import anthropic

from botcheck_scenarios import (
    ConversationTurn,
    RunReport,
    ScenarioDefinition,
    ScenarioType,
)

from .scoring import assemble_report, run_deterministic_checks, score_with_llm


def _entry_effective_score(entry: dict[str, Any]) -> float:
    metric_type = str(entry.get("metric_type", "score")).lower()
    if metric_type == "flag":
        passed = entry.get("passed")
        if passed is None:
            try:
                return float(entry.get("score", 0.0))
            except (TypeError, ValueError):
                return 0.0
        return 1.0 if bool(passed) else 0.0
    try:
        return float(entry.get("score", 0.0))
    except (TypeError, ValueError):
        return 0.0


def aggregate_scores_min(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge multiple judge responses by taking the minimum score per dimension."""
    if not samples:
        return {"scores": {}}

    dimensions: set[str] = set()
    for sample in samples:
        dimensions.update((sample.get("scores") or {}).keys())

    merged_scores: dict[str, dict[str, Any]] = {}
    for dimension in dimensions:
        best_entry: dict[str, Any] | None = None
        best_score = float("inf")
        for sample in samples:
            entry = (sample.get("scores") or {}).get(dimension)
            if not isinstance(entry, dict):
                # Dimension expected but absent in this sample: pessimistic default = 0.0.
                # This prevents a partial LLM response from hiding a potential failure.
                score = 0.0
                entry = None
            else:
                score = _entry_effective_score(entry)
            if score < best_score:
                best_score = score
                best_entry = dict(entry) if entry is not None else {"score": 0.0, "reasoning": "dimension absent in sample", "findings": []}
        if best_entry is not None:
            merged_scores[dimension] = best_entry

    return {
        "scores": merged_scores,
        "aggregation": {
            "strategy": "min",
            "samples": len(samples),
        },
    }


async def judge_conversation(
    *,
    run_id: str,
    scenario: ScenarioDefinition,
    conversation: list[ConversationTurn],
    tool_context: list[dict[str, Any]] | None = None,
    anthropic_client: anthropic.AsyncAnthropic,
    model: str = "claude-sonnet-4-6",
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    scenario_version_hash: str = "",
    tenant_id: str = "",
    judge_version: str = "0.1.0",
    taken_path_steps: list[dict[str, object]] | None = None,
    ai_context: dict[str, Any] | None = None,
    multi_sample_judge: bool = False,
    multi_sample_n: int = 3,
) -> tuple[RunReport, dict[str, int]]:
    now = datetime.now(UTC)
    started_at = started_at or now
    completed_at = completed_at or now

    deterministic = run_deterministic_checks(
        scenario,
        conversation,
        started_at,
        completed_at,
        taken_path_steps=taken_path_steps,
        bot_response_only=True,
    )

    total_usage = {"input_tokens": 0, "output_tokens": 0}

    use_multi_sample = (
        multi_sample_judge
        and scenario.type == ScenarioType.ADVERSARIAL
        and multi_sample_n > 1
    )
    if use_multi_sample:
        calls = [
            score_with_llm(
                client=anthropic_client,
                model=model,
                scenario=scenario,
                conversation=conversation,
                tool_context=tool_context,
                taken_path_steps=taken_path_steps,
                ai_context=ai_context,
            )
            for _ in range(multi_sample_n)
        ]
        results = await asyncio.gather(*calls)
        llm_samples = [r[0] for r in results]
        for _, usage in results:
            total_usage["input_tokens"] += usage.get("input_tokens", 0)
            total_usage["output_tokens"] += usage.get("output_tokens", 0)
        llm_scores = aggregate_scores_min(llm_samples)
    else:
        llm_scores, usage = await score_with_llm(
            client=anthropic_client,
            model=model,
            scenario=scenario,
            conversation=conversation,
            tool_context=tool_context,
            taken_path_steps=taken_path_steps,
            ai_context=ai_context,
        )
        total_usage["input_tokens"] = usage.get("input_tokens", 0)
        total_usage["output_tokens"] = usage.get("output_tokens", 0)

    report = assemble_report(
        run_id=run_id,
        scenario=scenario,
        scenario_version_hash=scenario_version_hash,
        tenant_id=tenant_id,
        conversation=conversation,
        deterministic=deterministic,
        llm_scores=llm_scores,
        started_at=started_at,
        completed_at=completed_at,
        judge_model=model,
        judge_version=judge_version,
        taken_path_steps=taken_path_steps,
    )
    return report, total_usage
