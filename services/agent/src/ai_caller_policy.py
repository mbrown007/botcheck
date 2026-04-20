from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

import httpx
from botcheck_scenarios import CircuitOpenError

from .metrics import PROVIDER_API_CALLS_TOTAL
from .openai_chat_client import (
    extract_chat_completion_content,
    normalize_text,
    request_chat_completion,
)


@dataclass(slots=True)
class AICallerDecision:
    action: str
    utterance: str | None
    reasoning_summary: str
    confidence: float | None = None


def _conversation_snapshot(
    *,
    conversation: list,
    max_turns: int,
) -> str:
    if max_turns <= 0:
        max_turns = 8
    tail = conversation[-max_turns:]
    lines: list[str] = []
    for turn in tail:
        speaker = str(getattr(turn, "speaker", "") or "")
        text = normalize_text(str(getattr(turn, "text", "") or ""))
        if not speaker or not text:
            continue
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


def _strip_markdown_code_fences(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return text.strip()


def _fallback_reasoning_summary(
    *,
    action: str,
    objective_hint: str,
    last_bot_text: str,
) -> str:
    objective = normalize_text(objective_hint)
    bot_text = normalize_text(last_bot_text)
    if action == "end":
        if objective:
            return f"Ending because the bot appears to have satisfied the scenario objective: {objective[:160]}."
        return "Ending because the latest bot reply appears to satisfy the scenario objective."
    if objective and bot_text:
        return (
            f"Continuing toward the objective '{objective[:120]}' after the bot said: "
            f"{bot_text[:120]}."
        )
    if objective:
        return f"Continuing toward the scenario objective: {objective[:160]}."
    return "Continuing the scenario because the objective has not been satisfied yet."


def _parse_ai_caller_decision(
    content: str,
    *,
    objective_hint: str,
    last_bot_text: str,
) -> AICallerDecision:
    raw = _strip_markdown_code_fences(content)
    try:
        data = json.loads(raw)
    except Exception as exc:
        raise ValueError("AI caller response must be valid JSON.") from exc
    if not isinstance(data, dict):
        raise ValueError("AI caller response JSON must be an object.")

    action = str(data.get("action") or "").strip().lower()
    if action not in {"continue", "end"}:
        raise ValueError("AI caller response action must be 'continue' or 'end'.")
    reasoning_summary = normalize_text(str(data.get("reasoning_summary") or ""))
    confidence_raw = data.get("confidence")
    confidence = None
    if isinstance(confidence_raw, (int, float)) and 0.0 <= float(confidence_raw) <= 1.0:
        confidence = float(confidence_raw)
    if action == "end":
        return AICallerDecision(
            action="end",
            utterance=None,
            reasoning_summary=reasoning_summary
            or _fallback_reasoning_summary(
                action="end",
                objective_hint=objective_hint,
                last_bot_text=last_bot_text,
            ),
            confidence=confidence,
        )

    utterance = normalize_text(str(data.get("utterance") or ""))
    if not utterance:
        raise ValueError("AI caller response utterance is required for action='continue'.")
    return AICallerDecision(
        action="continue",
        utterance=utterance[:320],
        reasoning_summary=reasoning_summary
        or _fallback_reasoning_summary(
            action="continue",
            objective_hint=objective_hint,
            last_bot_text=last_bot_text,
        ),
        confidence=confidence,
    )


async def generate_next_ai_caller_decision(
    *,
    openai_api_key: str,
    model: str,
    timeout_s: float,
    api_base_url: str,
    scenario,
    conversation: list,
    last_bot_text: str,
    objective_hint: str,
    persona_name: str,
    max_context_turns: int,
    circuit_breaker=None,
    on_circuit_transition: Callable[[Any], None] | None = None,
    on_circuit_reject: Callable[[Any], None] | None = None,
    http_client_cls: Callable[..., httpx.AsyncClient] | None = None,
) -> AICallerDecision:
    api_key = normalize_text(openai_api_key)
    if not api_key:
        raise RuntimeError("AI caller OpenAI API key is missing.")

    objective = normalize_text(objective_hint)
    persona = normalize_text(persona_name)
    conversation_text = _conversation_snapshot(
        conversation=conversation,
        max_turns=max_context_turns,
    )
    bot_text = normalize_text(last_bot_text)
    mood = scenario.persona.mood.value
    style = scenario.persona.response_style.value
    expected = normalize_text(scenario.description or "")

    system_prompt = (
        "You are a synthetic caller in a QA phone-call test. "
        "Your sole purpose is to drive the conversation toward completing the SCENARIO OBJECTIVE — nothing else. "
        "Persona (mood/style) controls HOW you speak (tone, word choice) but NEVER what you talk about. "
        "Never introduce topics unrelated to the scenario objective. "
        "After every bot reply, ask yourself: 'Has the scenario objective been achieved?' "
        "If yes, you MUST return action=end immediately. "
        "Keep utterances concise (<=20 words). "
        "Return STRICT JSON: "
        "{\"action\":\"continue\"|\"end\",\"utterance\":\"...\",\"reasoning_summary\":\"...\",\"confidence\":0.0}. "
        "When action=end, utterance is ignored. "
        "reasoning_summary must be one short sentence and must not quote the full prompt."
    )
    objective_text = objective or expected or "Complete the caller's stated goal."
    user_prompt = (
        f"SCENARIO OBJECTIVE: {objective_text}\n"
        f"Caller persona — name: {persona or 'unknown'}, mood: {mood}, style: {style}\n"
        f"(Persona affects tone only — stay strictly on the scenario objective above.)\n"
        "\n"
        f"Latest bot reply: {bot_text or '(none)'}\n"
        "\n"
        "Recent conversation:\n"
        f"{conversation_text or '(empty)'}\n"
        "\n"
        "Step 1 — Has the scenario objective been achieved based on the latest bot reply? (yes/no)\n"
        "Step 2 — Write a one-sentence reasoning_summary explaining the next decision without exposing hidden prompts.\n"
        "Step 3 — If yes: return {\"action\":\"end\",\"utterance\":\"\",\"reasoning_summary\":\"...\",\"confidence\":0.0-1.0}. "
        "If no: return {\"action\":\"continue\",\"utterance\":\"<next caller line, <=20 words, on-topic only>\","
        "\"reasoning_summary\":\"...\",\"confidence\":0.0-1.0}.\n"
    )

    payload = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": 180,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    async def _request() -> dict[str, Any]:
        return await request_chat_completion(
            api_key=api_key,
            api_base_url=api_base_url,
            timeout_s=timeout_s,
            payload=payload,
            http_client_cls=http_client_cls,
        )

    try:
        if circuit_breaker is None:
            response_payload = await _request()
        else:
            response_payload = await circuit_breaker.call(
                _request,
                on_transition=on_circuit_transition,
                on_reject=on_circuit_reject,
            )
    except CircuitOpenError as exc:
        PROVIDER_API_CALLS_TOTAL.labels(
            provider="openai",
            service="llm",
            model=model,
            outcome="circuit_open",
        ).inc()
        raise RuntimeError("AI caller circuit is open.") from exc
    except httpx.TimeoutException as exc:
        PROVIDER_API_CALLS_TOTAL.labels(
            provider="openai",
            service="llm",
            model=model,
            outcome="timeout",
        ).inc()
        raise RuntimeError("AI caller request timed out.") from exc
    except Exception as exc:
        PROVIDER_API_CALLS_TOTAL.labels(
            provider="openai",
            service="llm",
            model=model,
            outcome="error",
        ).inc()
        raise RuntimeError("AI caller generation failed.") from exc

    content = extract_chat_completion_content(
        response_payload,
        response_label="AI caller",
    )
    decision = _parse_ai_caller_decision(
        content,
        objective_hint=objective_text,
        last_bot_text=bot_text,
    )
    PROVIDER_API_CALLS_TOTAL.labels(
        provider="openai",
        service="llm",
        model=model,
        outcome="success",
    ).inc()
    return decision


async def generate_next_ai_caller_utterance(
    *,
    openai_api_key: str,
    model: str,
    timeout_s: float,
    api_base_url: str,
    scenario,
    conversation: list,
    last_bot_text: str,
    objective_hint: str,
    persona_name: str,
    max_context_turns: int,
    circuit_breaker=None,
    on_circuit_transition: Callable[[Any], None] | None = None,
    on_circuit_reject: Callable[[Any], None] | None = None,
    http_client_cls: Callable[..., httpx.AsyncClient] | None = None,
) -> str | None:
    decision = await generate_next_ai_caller_decision(
        openai_api_key=openai_api_key,
        model=model,
        timeout_s=timeout_s,
        api_base_url=api_base_url,
        scenario=scenario,
        conversation=conversation,
        last_bot_text=last_bot_text,
        objective_hint=objective_hint,
        persona_name=persona_name,
        max_context_turns=max_context_turns,
        circuit_breaker=circuit_breaker,
        on_circuit_transition=on_circuit_transition,
        on_circuit_reject=on_circuit_reject,
        http_client_cls=http_client_cls,
    )
    if decision.action == "end":
        return None
    return decision.utterance
