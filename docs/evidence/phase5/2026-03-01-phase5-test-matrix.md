# Phase 5 Test Matrix Evidence (2026-03-01)

## Scope
Automated coverage for backlog item 76 plus manual SIP sign-off checklist handoff.

## Automated Proofs (Passed)

1. Linear parity regression suite
- `services/agent/tests/test_graph.py::test_build_turn_sequence_linear_parity`
- Confirms graph mode preserves legacy linear execution order.

2. Branching mock multi-path suite
- `services/agent/tests/test_run_scenario_cache.py::test_run_scenario_branching_uses_classifier_and_reports_branch_metadata`
- `services/agent/tests/test_run_scenario_cache.py::test_run_scenario_branching_default_fallback_path`
- Confirms runtime branch selection and default fallback produce distinct taken paths.

3. Distinct loop failure end reasons
- `services/agent/tests/test_final_ack.py::TestLoopGuardPayload::test_build_loop_guard_payload_from_max_turns_error`
- `services/agent/tests/test_final_ack.py::TestLoopGuardPayload::test_build_loop_guard_payload_from_loop_error`
- `services/api/unit_tests/test_runs_loop_guard.py`
- Confirms `max_turns_reached` and `per_turn_loop_limit` are distinct and persisted.

4. Fail-closed missing-path contract
- `services/judge/tests/test_worker.py::test_payload_validation_rejects_branching_with_empty_taken_path_steps`
- `services/judge/tests/test_worker.py::test_judge_run_invalid_branching_payload_applies_fail_closed_patch`
- Confirms branching payloads with missing/empty path metadata are rejected and patched fail-closed.

5. Classifier normalized-match and timeout-fallthrough
- `services/agent/tests/test_branch_classifier.py::test_classify_branch_success_normalizes_choice`
- `services/agent/tests/test_branch_classifier.py::test_classify_branch_timeout_falls_back_to_default`

6. Branch-snippet redaction pipeline (truncation + API redaction)
- `services/api/unit_tests/test_runs_branch_snippet.py`
- `services/api/tests/test_runs.py::TestDuplicateTurnIdempotency::test_branch_decision_event_is_redacted_and_turn_payload_stays_clean`
- `services/api/tests/test_runs.py::TestDuplicateTurnIdempotency::test_branch_decision_event_truncates_then_redacts_snippet`
- Confirms harness snippet data is not persisted on transcript turns, branch detail is redacted, and stored snippet length is bounded to <=120 characters.

7. Multi-visit `turn.expect` fixtures
- `services/judge/tests/test_deterministic.py::TestForbiddenPhrases::test_multi_visit_expect_all_visits_pass`
- `services/judge/tests/test_deterministic.py::TestForbiddenPhrases::test_multi_visit_expect_fails_when_one_visit_contains_forbidden_phrase`
- Confirms all-visits-must-pass semantics for repeated visits.

8. Phase 7 closure dependency (all-arms pre-warm for branching scenarios)
- `services/judge/tests/test_cache_worker.py::test_warm_tts_cache_branching_scenario_precaches_all_harness_arms`
- Confirms pre-warm includes all harness arms, including branches that may be unexecuted in a single run.

9. Follow-up hardening assertion for future deterministic `turn.expect` expansion
- `services/judge/tests/test_deterministic.py::TestForbiddenPhrases::test_path_scoping_hardening_registry_for_turn_expectations`
- Guardrail: when deterministic checks expand beyond `no_forbidden_phrase`, path-scoped fixtures must be updated alongside the new field coverage.

## Gate Script

- `scripts/ci/phase5_test_matrix.sh` runs the targeted matrix and is wired into CI (`.github/workflows/ci.yml`).

## Command Output Snapshot

```bash
bash scripts/ci/phase5_test_matrix.sh
# INFO [phase5_test_matrix.sh] Phase 5 matrix checks passed
```

## Manual Evidence Link

- SIP live branching sign-off checklist:
  `docs/evidence/phase5/sip-branching-signoff.md`
