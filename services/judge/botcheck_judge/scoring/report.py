"""
Report assembly — maps raw LLM scores + deterministic checks into a RunReport.

Pure function: no I/O, no side effects.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import NamedTuple

from botcheck_scenarios import (
    ConversationTurn,
    DeterministicChecks,
    DimensionScore,
    Finding,
    GateResult,
    MetricType,
    RunReport,
    RunStatus,
    ScenarioDefinition,
    ScoringDimension,
    Severity,
    resolve_rubric,
)

logger = logging.getLogger("botcheck.judge.report")


class _PathCoordinate(NamedTuple):
    turn_id: str
    turn_number: int
    visit: int | None


def _coerce_positive_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _path_coordinates_by_turn_number(
    conversation: list[ConversationTurn],
    taken_path_steps: list[dict[str, object]] | None,
) -> dict[int, _PathCoordinate]:
    coords: dict[int, _PathCoordinate] = {}
    if taken_path_steps:
        for raw in taken_path_steps:
            if not isinstance(raw, dict):
                continue
            turn_id = str(raw.get("turn_id") or "").strip()
            turn_number = _coerce_positive_int(raw.get("turn_number"))
            visit = _coerce_positive_int(raw.get("visit"))
            if not turn_id or turn_number is None:
                continue
            coords.setdefault(
                turn_number,
                _PathCoordinate(
                    turn_id=turn_id,
                    turn_number=turn_number,
                    visit=visit,
                ),
            )

    seen_by_turn_id: dict[str, int] = {}
    for turn in conversation:
        seen_by_turn_id[turn.turn_id] = seen_by_turn_id.get(turn.turn_id, 0) + 1
        coords.setdefault(
            turn.turn_number,
            _PathCoordinate(
                turn_id=turn.turn_id,
                turn_number=turn.turn_number,
                visit=seen_by_turn_id[turn.turn_id],
            ),
        )
    return coords


def _resolved_finding_coordinates(
    *,
    raw_finding: dict[str, object],
    path_coords: dict[int, _PathCoordinate],
) -> _PathCoordinate:
    raw_turn_number = _coerce_positive_int(raw_finding.get("turn_number")) or 0
    mapped = path_coords.get(raw_turn_number)

    raw_turn_id = str(raw_finding.get("turn_id") or "").strip()
    raw_visit = _coerce_positive_int(raw_finding.get("visit"))

    if mapped is not None:
        return _PathCoordinate(
            turn_id=raw_turn_id or mapped.turn_id,
            turn_number=mapped.turn_number,
            visit=raw_visit if raw_visit is not None else mapped.visit,
        )
    if raw_turn_number > 0:
        return _PathCoordinate(
            turn_id=raw_turn_id or f"t{raw_turn_number}",
            turn_number=raw_turn_number,
            visit=raw_visit,
        )
    return _PathCoordinate(turn_id=raw_turn_id or "unknown", turn_number=0, visit=raw_visit)


def _resolve_turn_coordinate(
    turn: ConversationTurn,
    path_coords: dict[int, _PathCoordinate],
) -> _PathCoordinate:
    return path_coords.get(
        turn.turn_number,
        _PathCoordinate(
            turn_id=turn.turn_id,
            turn_number=turn.turn_number,
            visit=None,
        ),
    )


def assemble_report(
    *,
    run_id: str,
    scenario: ScenarioDefinition,
    scenario_version_hash: str,
    tenant_id: str,
    conversation: list[ConversationTurn],
    deterministic: DeterministicChecks,
    llm_scores: dict,
    started_at: datetime,
    completed_at: datetime,
    judge_model: str,
    judge_version: str,
    taken_path_steps: list[dict[str, object]] | None = None,
) -> RunReport:
    rubric = resolve_rubric(scenario.type, scenario.scoring.rubric)
    rubric_map = {r.dimension: r for r in rubric}

    raw_scores = llm_scores.get("scores", {})
    if not raw_scores:
        raise ValueError("Judge returned no scores")

    scores: dict[str, DimensionScore] = {}
    all_findings: list[Finding] = []
    path_coords = _path_coordinates_by_turn_number(conversation, taken_path_steps)

    for dim_str, raw in raw_scores.items():
        try:
            dim = ScoringDimension(dim_str)
        except ValueError:
            logger.warning("Unknown scoring dimension from LLM: %r - skipping", dim_str)
            continue

        rubric_entry = rubric_map.get(dim)
        if rubric_entry is None:
            continue

        metric_type_str = str(raw.get("metric_type", MetricType.SCORE.value)).lower()
        if metric_type_str == MetricType.FLAG.value:
            metric_type = MetricType.FLAG
        elif metric_type_str == MetricType.SCORE.value:
            metric_type = MetricType.SCORE
        else:
            logger.warning(
                "Unknown metric_type %r for dimension %r; defaulting to 'score'",
                metric_type_str,
                dim_str,
            )
            metric_type = MetricType.SCORE

        if metric_type == MetricType.FLAG:
            passed_raw = raw.get("passed")
            if passed_raw is None:
                score_val = float(raw.get("score", 0.0))
                passed = score_val >= rubric_entry.threshold
            else:
                passed = bool(passed_raw)
                score_val = 1.0 if passed else 0.0
            status = RunStatus.PASS if passed else RunStatus.FAIL
        else:
            score_val = float(raw.get("score", 0.0))
            passed = None
            status = (
                RunStatus.PASS if score_val >= rubric_entry.threshold else RunStatus.FAIL
            )

        findings: list[Finding] = []
        for f in raw.get("findings", []):
            if not isinstance(f, dict):
                continue
            coord = _resolved_finding_coordinates(
                raw_finding=f,
                path_coords=path_coords,
            )
            finding = Finding(
                dimension=dim,
                turn_id=coord.turn_id,
                turn_number=coord.turn_number,
                visit=coord.visit,
                speaker=f.get("speaker", "bot"),
                quoted_text=f.get("quoted_text", ""),
                finding=f.get("finding", ""),
                severity=_parse_severity(f.get("severity", "medium")),
                positive=bool(f.get("positive", False)),
            )
            findings.append(finding)
            all_findings.append(finding)

        scores[dim_str] = DimensionScore(
            metric_type=metric_type,
            score=score_val,
            passed=passed,
            status=status,
            threshold=rubric_entry.threshold,
            gate=rubric_entry.gate,
            findings=findings,
            reasoning=raw.get("reasoning", ""),
        )

    if not scores:
        raise ValueError("Judge returned only unknown dimensions")

    timing_findings = _apply_reliability_timing_overrides(
        scenario=scenario,
        conversation=conversation,
        deterministic=deterministic,
        rubric_map=rubric_map,
        scores=scores,
        path_coords=path_coords,
    )
    all_findings.extend(timing_findings)
    role_findings = _apply_role_integrity_overrides(
        deterministic=deterministic,
        conversation=conversation,
        rubric_map=rubric_map,
        scores=scores,
        path_coords=path_coords,
    )
    all_findings.extend(role_findings)

    gate_blocked = any(
        s.gate and s.status == RunStatus.FAIL for s in scores.values()
    )
    overall_status = RunStatus.FAIL if gate_blocked else RunStatus.PASS
    gate_result = (
        GateResult.BLOCKED
        if (gate_blocked and scenario.scoring.overall_gate)
        else GateResult.PASSED
    )

    return RunReport(
        run_id=run_id,
        scenario_id=scenario.id,
        scenario_version_hash=scenario_version_hash,
        bot_endpoint=scenario.bot.endpoint,
        tenant_id=tenant_id,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=int((completed_at - started_at).total_seconds() * 1000),
        overall_status=overall_status,
        gate_result=gate_result,
        scores=scores,
        deterministic=deterministic,
        conversation=conversation,
        all_findings=all_findings,
        judge_model=judge_model,
        judge_version=judge_version,
    )


def _parse_severity(value: str) -> Severity:
    try:
        return Severity(value.lower())
    except ValueError:
        return Severity.MEDIUM


def _conversation_gaps(
    conversation: list[ConversationTurn],
) -> list[tuple[ConversationTurn, ConversationTurn, int]]:
    gaps: list[tuple[ConversationTurn, ConversationTurn, int]] = []
    prev: ConversationTurn | None = None
    for turn in conversation:
        if prev is not None and turn.speaker != prev.speaker:
            gap_ms = int(turn.audio_start_ms) - int(prev.audio_end_ms)
            gaps.append((prev, turn, gap_ms))
        prev = turn
    return gaps


def _bounded_score(value: float) -> float:
    return max(0.0, min(1.0, value))


def _score_metric_high_is_bad(
    *,
    actual: float,
    warn_threshold: float,
    gate_threshold: float,
) -> float:
    if actual <= warn_threshold:
        return 1.0
    if actual <= gate_threshold:
        span = max(gate_threshold - warn_threshold, 1.0)
        progress = (actual - warn_threshold) / span
        return _bounded_score(1.0 - (0.2 * progress))
    return _bounded_score(0.8 * (gate_threshold / max(actual, 1.0)))


def _score_metric_low_is_bad(
    *,
    actual: float,
    warn_threshold: float,
    gate_threshold: float,
) -> float:
    if actual >= warn_threshold:
        return 1.0
    if actual >= gate_threshold:
        span = max(warn_threshold - gate_threshold, 1e-6)
        progress = (warn_threshold - actual) / span
        return _bounded_score(1.0 - (0.2 * progress))
    return _bounded_score(0.8 * (actual / max(gate_threshold, 1e-6)))


def _apply_reliability_timing_overrides(
    *,
    scenario: ScenarioDefinition,
    conversation: list[ConversationTurn],
    deterministic: DeterministicChecks,
    rubric_map: dict[ScoringDimension, object],
    scores: dict[str, DimensionScore],
    path_coords: dict[int, _PathCoordinate],
) -> list[Finding]:
    reliability_rubric = rubric_map.get(ScoringDimension.RELIABILITY)
    if reliability_rubric is None:
        return []

    interruptions = deterministic.interruptions_count
    long_pauses = deterministic.long_pause_count
    p95_gap = deterministic.p95_response_gap_ms
    recovery_pct = deterministic.interruption_recovery_pct
    efficiency_pct = deterministic.turn_taking_efficiency_pct
    if (
        interruptions is None
        or long_pauses is None
        or p95_gap is None
        or recovery_pct is None
        or efficiency_pct is None
    ):
        return []

    gaps = _conversation_gaps(conversation)
    findings: list[Finding] = []
    failures: list[str] = []
    warnings: list[str] = []

    if p95_gap > scenario.config.timing_gate_p95_response_gap_ms:
        failures.append(
            f"p95_response_gap_ms={p95_gap} > {scenario.config.timing_gate_p95_response_gap_ms}"
        )
        if gaps:
            _, turn, _ = max(gaps, key=lambda item: item[2])
            coord = _resolve_turn_coordinate(turn, path_coords)
            findings.append(
                Finding(
                    dimension=ScoringDimension.RELIABILITY,
                    turn_id=coord.turn_id,
                    turn_number=coord.turn_number,
                    visit=coord.visit,
                    speaker=turn.speaker,
                    quoted_text=turn.text,
                    finding=(
                        "Response latency exceeded gate threshold "
                        f"(p95_response_gap_ms={p95_gap})."
                    ),
                    severity=Severity.HIGH,
                    positive=False,
                )
            )
    elif p95_gap > scenario.config.timing_warn_p95_response_gap_ms:
        warnings.append(
            f"p95_response_gap_ms={p95_gap} > {scenario.config.timing_warn_p95_response_gap_ms}"
        )

    if recovery_pct < scenario.config.timing_gate_interruption_recovery_pct:
        failures.append(
            "interruption_recovery_pct="
            f"{recovery_pct:.2f} < {scenario.config.timing_gate_interruption_recovery_pct:.2f}"
        )
        interruption_event = next((item for item in gaps if item[2] <= 0), None)
        if interruption_event is not None:
            _, turn, gap_ms = interruption_event
            coord = _resolve_turn_coordinate(turn, path_coords)
            findings.append(
                Finding(
                    dimension=ScoringDimension.RELIABILITY,
                    turn_id=coord.turn_id,
                    turn_number=coord.turn_number,
                    visit=coord.visit,
                    speaker=turn.speaker,
                    quoted_text=turn.text,
                    finding=(
                        "Interruption recovery below gate threshold "
                        f"(interruption_recovery_pct={recovery_pct:.2f}, gap_ms={gap_ms})."
                    ),
                    severity=Severity.HIGH,
                    positive=False,
                )
            )
    elif recovery_pct < scenario.config.timing_warn_interruption_recovery_pct:
        warnings.append(
            "interruption_recovery_pct="
            f"{recovery_pct:.2f} < {scenario.config.timing_warn_interruption_recovery_pct:.2f}"
        )

    if efficiency_pct < scenario.config.timing_gate_turn_taking_efficiency_pct:
        failures.append(
            "turn_taking_efficiency_pct="
            f"{efficiency_pct:.2f} < {scenario.config.timing_gate_turn_taking_efficiency_pct:.2f}"
        )
        long_pause_event = max(gaps, key=lambda item: item[2], default=None)
        if long_pause_event is not None:
            _, turn, gap_ms = long_pause_event
            coord = _resolve_turn_coordinate(turn, path_coords)
            findings.append(
                Finding(
                    dimension=ScoringDimension.RELIABILITY,
                    turn_id=coord.turn_id,
                    turn_number=coord.turn_number,
                    visit=coord.visit,
                    speaker=turn.speaker,
                    quoted_text=turn.text,
                    finding=(
                        "Turn-taking efficiency below gate threshold "
                        f"(turn_taking_efficiency_pct={efficiency_pct:.2f}, gap_ms={gap_ms})."
                    ),
                    severity=Severity.MEDIUM,
                    positive=False,
                )
            )
    elif efficiency_pct < scenario.config.timing_warn_turn_taking_efficiency_pct:
        warnings.append(
            "turn_taking_efficiency_pct="
            f"{efficiency_pct:.2f} < {scenario.config.timing_warn_turn_taking_efficiency_pct:.2f}"
        )

    component_scores = [
        _score_metric_high_is_bad(
            actual=float(p95_gap),
            warn_threshold=float(scenario.config.timing_warn_p95_response_gap_ms),
            gate_threshold=float(scenario.config.timing_gate_p95_response_gap_ms),
        ),
        _score_metric_low_is_bad(
            actual=float(recovery_pct),
            warn_threshold=float(scenario.config.timing_warn_interruption_recovery_pct),
            gate_threshold=float(scenario.config.timing_gate_interruption_recovery_pct),
        ),
        _score_metric_low_is_bad(
            actual=float(efficiency_pct),
            warn_threshold=float(scenario.config.timing_warn_turn_taking_efficiency_pct),
            gate_threshold=float(scenario.config.timing_gate_turn_taking_efficiency_pct),
        ),
    ]
    deterministic_score = round(sum(component_scores) / len(component_scores), 4)
    status = RunStatus.PASS
    if failures:
        status = RunStatus.FAIL
    elif warnings:
        status = RunStatus.WARN

    reliability_key = ScoringDimension.RELIABILITY.value
    existing = scores.get(reliability_key)
    summary_parts = [
        "timing("
        f"p95_gap_ms={p95_gap}, "
        f"interruptions={interruptions}, "
        f"long_pauses={long_pauses}, "
        f"interruption_recovery_pct={recovery_pct:.2f}, "
        f"turn_taking_efficiency_pct={efficiency_pct:.2f})"
    ]
    if failures:
        summary_parts.append("failures=" + "; ".join(failures))
    elif warnings:
        summary_parts.append("warnings=" + "; ".join(warnings))
    else:
        summary_parts.append("timing_within_thresholds")
    timing_reasoning = " | ".join(summary_parts)

    if existing is None:
        scores[reliability_key] = DimensionScore(
            metric_type=MetricType.SCORE,
            score=deterministic_score,
            passed=None,
            status=status,
            threshold=float(getattr(reliability_rubric, "threshold")),
            gate=bool(getattr(reliability_rubric, "gate")),
            findings=findings,
            reasoning=timing_reasoning,
        )
        return findings

    existing_score = existing.score
    if existing_score is None:
        existing_score = 1.0 if existing.passed else 0.0
    merged_score = min(existing_score, deterministic_score)
    merged_status = existing.status
    if status == RunStatus.FAIL:
        merged_status = RunStatus.FAIL
    elif status == RunStatus.WARN and existing.status == RunStatus.PASS:
        merged_status = RunStatus.WARN

    merged_reasoning = (
        f"{existing.reasoning} | {timing_reasoning}"
        if existing.reasoning
        else timing_reasoning
    )
    scores[reliability_key] = DimensionScore(
        metric_type=existing.metric_type,
        score=merged_score,
        passed=existing.passed,
        status=merged_status,
        threshold=existing.threshold,
        gate=existing.gate,
        findings=[*existing.findings, *findings],
        reasoning=merged_reasoning,
    )
    return findings


def _apply_role_integrity_overrides(
    *,
    deterministic: DeterministicChecks,
    conversation: list[ConversationTurn],
    rubric_map: dict[ScoringDimension, object],
    scores: dict[str, DimensionScore],
    path_coords: dict[int, _PathCoordinate],
) -> list[Finding]:
    role_rubric = rubric_map.get(ScoringDimension.ROLE_INTEGRITY)
    if role_rubric is None:
        return []

    not_switched = deterministic.not_role_switched
    if not_switched is None:
        return []

    role_turn_ids = set(deterministic.role_switch_turns)
    findings: list[Finding] = []
    if role_turn_ids:
        for turn in conversation:
            if turn.turn_id not in role_turn_ids:
                continue
            coord = _resolve_turn_coordinate(turn, path_coords)
            findings.append(
                Finding(
                    dimension=ScoringDimension.ROLE_INTEGRITY,
                    turn_id=coord.turn_id,
                    turn_number=coord.turn_number,
                    visit=coord.visit,
                    speaker=turn.speaker,
                    quoted_text=turn.text,
                    finding=(
                        "Bot response appears to assume the caller role "
                        "(role switch detected)."
                    ),
                    severity=Severity.HIGH,
                    positive=False,
                )
            )

    deterministic_score = 1.0 if not_switched else 0.0
    deterministic_status = RunStatus.PASS if not_switched else RunStatus.FAIL
    deterministic_reasoning = (
        "role_integrity(not_role_switched=true)"
        if not_switched
        else f"role_integrity(not_role_switched=false, turns={sorted(role_turn_ids)})"
    )

    role_key = ScoringDimension.ROLE_INTEGRITY.value
    existing = scores.get(role_key)
    if existing is None:
        scores[role_key] = DimensionScore(
            metric_type=MetricType.FLAG,
            score=deterministic_score,
            passed=not_switched,
            status=deterministic_status,
            threshold=float(getattr(role_rubric, "threshold")),
            gate=bool(getattr(role_rubric, "gate")),
            findings=findings,
            reasoning=deterministic_reasoning,
        )
        return findings

    existing_score = existing.score
    if existing_score is None:
        existing_score = 1.0 if existing.passed else 0.0
    merged_score = min(existing_score, deterministic_score)
    merged_status = existing.status if not_switched else RunStatus.FAIL

    merged_passed = existing.passed
    if existing.metric_type == MetricType.FLAG:
        existing_passed = (
            existing.passed
            if existing.passed is not None
            else (existing_score >= existing.threshold)
        )
        merged_passed = existing_passed and not_switched

    merged_reasoning = (
        f"{existing.reasoning} | {deterministic_reasoning}"
        if existing.reasoning
        else deterministic_reasoning
    )
    scores[role_key] = DimensionScore(
        metric_type=existing.metric_type,
        score=merged_score,
        passed=merged_passed,
        status=merged_status,
        threshold=existing.threshold,
        gate=existing.gate,
        findings=[*existing.findings, *findings],
        reasoning=merged_reasoning,
    )
    return findings
