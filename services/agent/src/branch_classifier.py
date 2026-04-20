from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Protocol

from .metrics import (
    BRANCH_CLASSIFIER_CALLS_TOTAL,
    BRANCH_CLASSIFIER_LATENCY_SECONDS,
)

logger = logging.getLogger("botcheck.agent.branch_classifier")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


class BranchClassifierClient(Protocol):
    async def choose_condition(
        self,
        *,
        bot_response: str,
        conditions: list[str],
        conversation_history: list[dict] | None,
        scenario_intent: str,
        model: str,
    ) -> str: ...


def _normalize_condition(value: str) -> str:
    return value.strip().lower()


def _tokenize(value: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall(value.lower()) if token}


class HeuristicBranchClassifierClient:
    """
    Deterministic branch classifier used by default harness runtime.

    Picks the condition with the highest token-overlap with bot_response.
    Returns "default" when no condition has positive overlap.
    """

    async def choose_condition(
        self,
        *,
        bot_response: str,
        conditions: list[str],
        conversation_history: list[dict] | None,
        scenario_intent: str,
        model: str,
    ) -> str:
        del conversation_history, scenario_intent, model
        response_tokens = _tokenize(bot_response)
        if not response_tokens:
            return "default"

        best_condition = "default"
        best_score = 0
        for condition in conditions:
            condition_tokens = _tokenize(condition)
            if not condition_tokens:
                continue
            score = len(response_tokens.intersection(condition_tokens))
            if score > best_score:
                best_score = score
                best_condition = condition
        return best_condition if best_score > 0 else "default"


async def classify_branch(
    *,
    bot_response: str,
    conditions: list[str],
    conversation_history: list[dict] | None,
    scenario_intent: str,
    client: BranchClassifierClient,
    model: str,
    timeout_s: float,
) -> str:
    """
    Return one of `conditions` or `"default"` on timeout/error/no-match.

    The classifier is best-effort: failures never abort run execution.
    """
    if not conditions:
        return "default"

    normalised_to_original = {_normalize_condition(condition): condition for condition in conditions}
    started = time.monotonic()
    outcome = "success"
    try:
        raw = await asyncio.wait_for(
            client.choose_condition(
                bot_response=bot_response,
                conditions=conditions,
                conversation_history=conversation_history,
                scenario_intent=scenario_intent,
                model=model,
            ),
            timeout=timeout_s,
        )
        chosen = normalised_to_original.get(_normalize_condition(raw), "default")
        return chosen
    except asyncio.TimeoutError:
        outcome = "timeout"
        logger.warning("branch_classifier.timeout — falling through to default")
        return "default"
    except Exception:
        outcome = "error"
        logger.warning(
            "branch_classifier.error — falling through to default",
            exc_info=True,
        )
        return "default"
    finally:
        elapsed_s = time.monotonic() - started
        BRANCH_CLASSIFIER_CALLS_TOTAL.labels(outcome=outcome).inc()
        BRANCH_CLASSIFIER_LATENCY_SECONDS.labels(outcome=outcome).observe(elapsed_s)
