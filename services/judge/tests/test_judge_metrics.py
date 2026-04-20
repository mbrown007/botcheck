import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("S3_ACCESS_KEY", "test")
os.environ.setdefault("S3_SECRET_KEY", "test")

from botcheck_judge.metrics import (
    JUDGE_LLM_LATENCY_SECONDS,
    SCENARIO_GATE_RESULTS_TOTAL,
    VOICE_QUALITY_INTERRUPTION_RECOVERY_PCT,
    VOICE_QUALITY_P95_RESPONSE_GAP_MILLISECONDS,
    VOICE_QUALITY_RUNS_TOTAL,
    VOICE_QUALITY_THRESHOLD_BREACHES_TOTAL,
    VOICE_QUALITY_TURN_TAKING_EFFICIENCY_PCT,
    observe_voice_quality_thresholds,
)


def _counter_value(counter, **labels):
    return counter.labels(**labels)._value.get()


def _hist_count(histogram, **labels):
    labeled = histogram.labels(**labels)
    for metric in labeled.collect():
        for sample in metric.samples:
            if sample.name.endswith("_count"):
                return sample.value
    raise AssertionError("Histogram count sample not found")


def _gauge_value(gauge, **labels):
    return gauge.labels(**labels)._value.get()


def test_judge_llm_latency_histogram_records_by_model_and_trigger_source():
    before = _hist_count(
        JUDGE_LLM_LATENCY_SECONDS,
        model="claude-sonnet-test",
        trigger_source="manual",
    )

    JUDGE_LLM_LATENCY_SECONDS.labels(
        model="claude-sonnet-test",
        trigger_source="manual",
    ).observe(0.75)

    assert (
        _hist_count(
            JUDGE_LLM_LATENCY_SECONDS,
            model="claude-sonnet-test",
            trigger_source="manual",
        )
        == before + 1
    )


def test_scenario_gate_results_counter_records_result_by_kind_and_trigger_source():
    before = _counter_value(
        SCENARIO_GATE_RESULTS_TOTAL,
        result="passed",
        scenario_kind="graph",
        trigger_source="scheduled",
    )

    SCENARIO_GATE_RESULTS_TOTAL.labels(
        result="passed",
        scenario_kind="graph",
        trigger_source="scheduled",
    ).inc()

    assert (
        _counter_value(
            SCENARIO_GATE_RESULTS_TOTAL,
            result="passed",
            scenario_kind="graph",
            trigger_source="scheduled",
        )
        == before + 1
    )


def test_observe_voice_quality_thresholds_records_gate_breaches():
    trigger_source = "scheduled"
    before_fail = _counter_value(
        VOICE_QUALITY_RUNS_TOTAL,
        result="fail",
        trigger_source=trigger_source,
    )
    before_p95_gate = _counter_value(
        VOICE_QUALITY_THRESHOLD_BREACHES_TOTAL,
        metric="p95_response_gap_ms",
        severity="gate",
        trigger_source=trigger_source,
    )
    before_recovery_gate = _counter_value(
        VOICE_QUALITY_THRESHOLD_BREACHES_TOTAL,
        metric="interruption_recovery_pct",
        severity="gate",
        trigger_source=trigger_source,
    )
    before_efficiency_gate = _counter_value(
        VOICE_QUALITY_THRESHOLD_BREACHES_TOTAL,
        metric="turn_taking_efficiency_pct",
        severity="gate",
        trigger_source=trigger_source,
    )
    before_recovery_hist = _hist_count(
        VOICE_QUALITY_INTERRUPTION_RECOVERY_PCT,
        trigger_source=trigger_source,
    )
    before_efficiency_hist = _hist_count(
        VOICE_QUALITY_TURN_TAKING_EFFICIENCY_PCT,
        trigger_source=trigger_source,
    )

    result = observe_voice_quality_thresholds(
        trigger_source=trigger_source,
        p95_response_gap_ms=1700,
        interruption_recovery_pct=72.0,
        turn_taking_efficiency_pct=80.0,
        timing_gate_p95_response_gap_ms=1200,
        timing_warn_p95_response_gap_ms=800,
        timing_gate_interruption_recovery_pct=90.0,
        timing_warn_interruption_recovery_pct=85.0,
        timing_gate_turn_taking_efficiency_pct=95.0,
        timing_warn_turn_taking_efficiency_pct=90.0,
    )

    assert result == "fail"
    assert (
        _counter_value(
            VOICE_QUALITY_RUNS_TOTAL,
            result="fail",
            trigger_source=trigger_source,
        )
        == before_fail + 1
    )
    assert (
        _counter_value(
            VOICE_QUALITY_THRESHOLD_BREACHES_TOTAL,
            metric="p95_response_gap_ms",
            severity="gate",
            trigger_source=trigger_source,
        )
        == before_p95_gate + 1
    )
    assert (
        _counter_value(
            VOICE_QUALITY_THRESHOLD_BREACHES_TOTAL,
            metric="interruption_recovery_pct",
            severity="gate",
            trigger_source=trigger_source,
        )
        == before_recovery_gate + 1
    )
    assert (
        _counter_value(
            VOICE_QUALITY_THRESHOLD_BREACHES_TOTAL,
            metric="turn_taking_efficiency_pct",
            severity="gate",
            trigger_source=trigger_source,
        )
        == before_efficiency_gate + 1
    )
    assert (
        _gauge_value(
            VOICE_QUALITY_P95_RESPONSE_GAP_MILLISECONDS,
            trigger_source=trigger_source,
        )
        == 1700.0
    )
    assert (
        _hist_count(
            VOICE_QUALITY_INTERRUPTION_RECOVERY_PCT,
            trigger_source=trigger_source,
        )
        == before_recovery_hist + 1
    )
    assert (
        _hist_count(
            VOICE_QUALITY_TURN_TAKING_EFFICIENCY_PCT,
            trigger_source=trigger_source,
        )
        == before_efficiency_hist + 1
    )


def test_observe_voice_quality_thresholds_records_warnings():
    trigger_source = "manual"
    before_warn = _counter_value(
        VOICE_QUALITY_RUNS_TOTAL,
        result="warn",
        trigger_source=trigger_source,
    )
    before_p95_warn = _counter_value(
        VOICE_QUALITY_THRESHOLD_BREACHES_TOTAL,
        metric="p95_response_gap_ms",
        severity="warn",
        trigger_source=trigger_source,
    )
    before_recovery_warn = _counter_value(
        VOICE_QUALITY_THRESHOLD_BREACHES_TOTAL,
        metric="interruption_recovery_pct",
        severity="warn",
        trigger_source=trigger_source,
    )
    before_efficiency_warn = _counter_value(
        VOICE_QUALITY_THRESHOLD_BREACHES_TOTAL,
        metric="turn_taking_efficiency_pct",
        severity="warn",
        trigger_source=trigger_source,
    )

    result = observe_voice_quality_thresholds(
        trigger_source=trigger_source,
        p95_response_gap_ms=900,
        interruption_recovery_pct=87.0,
        turn_taking_efficiency_pct=92.0,
        timing_gate_p95_response_gap_ms=1200,
        timing_warn_p95_response_gap_ms=800,
        timing_gate_interruption_recovery_pct=80.0,
        timing_warn_interruption_recovery_pct=90.0,
        timing_gate_turn_taking_efficiency_pct=85.0,
        timing_warn_turn_taking_efficiency_pct=95.0,
    )

    assert result == "warn"
    assert (
        _counter_value(
            VOICE_QUALITY_RUNS_TOTAL,
            result="warn",
            trigger_source=trigger_source,
        )
        == before_warn + 1
    )
    assert (
        _counter_value(
            VOICE_QUALITY_THRESHOLD_BREACHES_TOTAL,
            metric="p95_response_gap_ms",
            severity="warn",
            trigger_source=trigger_source,
        )
        == before_p95_warn + 1
    )
    assert (
        _counter_value(
            VOICE_QUALITY_THRESHOLD_BREACHES_TOTAL,
            metric="interruption_recovery_pct",
            severity="warn",
            trigger_source=trigger_source,
        )
        == before_recovery_warn + 1
    )
    assert (
        _counter_value(
            VOICE_QUALITY_THRESHOLD_BREACHES_TOTAL,
            metric="turn_taking_efficiency_pct",
            severity="warn",
            trigger_source=trigger_source,
        )
        == before_efficiency_warn + 1
    )
    assert (
        _gauge_value(
            VOICE_QUALITY_P95_RESPONSE_GAP_MILLISECONDS,
            trigger_source=trigger_source,
        )
        == 900.0
    )


def test_observe_voice_quality_thresholds_records_pass():
    trigger_source = "manual"
    before_pass = _counter_value(
        VOICE_QUALITY_RUNS_TOTAL,
        result="pass",
        trigger_source=trigger_source,
    )

    result = observe_voice_quality_thresholds(
        trigger_source=trigger_source,
        p95_response_gap_ms=550,
        interruption_recovery_pct=96.0,
        turn_taking_efficiency_pct=98.0,
        timing_gate_p95_response_gap_ms=1200,
        timing_warn_p95_response_gap_ms=800,
        timing_gate_interruption_recovery_pct=90.0,
        timing_warn_interruption_recovery_pct=85.0,
        timing_gate_turn_taking_efficiency_pct=95.0,
        timing_warn_turn_taking_efficiency_pct=90.0,
    )

    assert result == "pass"
    assert (
        _counter_value(
            VOICE_QUALITY_RUNS_TOTAL,
            result="pass",
            trigger_source=trigger_source,
        )
        == before_pass + 1
    )
    assert (
        _gauge_value(
            VOICE_QUALITY_P95_RESPONSE_GAP_MILLISECONDS,
            trigger_source=trigger_source,
        )
        == 550.0
    )
