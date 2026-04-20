# Phase 7 Test Matrix Evidence (2026-02-28)

## Scope
This evidence captures non-deferred Phase 7 automated coverage and current operational drill status.

## Automated Proofs (Passed)

1. Cache-hit zero-live-TTS execution (linear warm scenario)
- Test: `services/agent/tests/test_run_scenario_cache.py::test_run_scenario_fully_warm_uses_cache_without_live_tts`
- Evidence: run uses cached WAV for all harness turns; live `openai.TTS.synthesize()` call count remains `0`; cache hit counter increments per turn

2. S3/cache fallback without run abort
- Test: `services/agent/tests/test_run_scenario_cache.py::test_run_scenario_s3_fallback_uses_live_tts_without_abort`
- Evidence: cache read path returns `None`, harness falls back to live TTS, scenario run completes and reports turns

3. Partial scenario re-cache (modified turn only)
- Test: `services/judge/tests/test_cache_worker.py::test_warm_tts_cache_recaches_only_modified_turn`
- Evidence: unchanged turn is `skipped`, modified turn is synthesized and cached; manifest updates reflect `cached=1, skipped=1`

4. Cross-tenant key isolation
- Test: `services/judge/tests/test_cache_worker.py::test_warm_tts_cache_isolated_by_tenant_prefix`
- Evidence: warm jobs for same scenario under `tenant-a` and `tenant-b` produce separate key prefixes and independent cache objects

5. Worker payload contract (no scenario HTTP re-fetch)
- Test: `services/judge/tests/test_cache_worker.py::test_warm_tts_cache_uses_embedded_payload_without_http_fetch`
- Evidence: worker can complete warm flow using `scenario_payload` only; no direct HTTP client creation in this path

6. Queue isolation (`arq:cache` vs `arq:judge`)
- Scenario cache enqueue tests assert `_queue_name == "arq:cache"` for warm/rebuild/purge paths
- Run completion test asserts `_queue_name == "arq:judge"` for judge enqueue path (`test_complete_transitions_to_judging`)

7. Stale warm-job completion ignored by version-hash guard
- API sync endpoint test: `services/api/tests/test_scenarios.py::test_sync_ignores_stale_version_hash`
- Worker surface test: `services/judge/tests/test_cache_worker.py::test_warm_tts_cache_stale_sync_marks_status_not_applied`
- Evidence: stale version returns `reason="version_mismatch"` in sync API; warm job keeps `status_applied=False` when sync rejects stale completion

## Command Outputs

```bash
uv run pytest services/judge/tests -q
# 76 passed

uv run pytest services/agent/tests -q
# 14 passed

uv run pytest services/api/tests/test_runs.py::TestCompleteAndGate::test_complete_transitions_to_judging -q
# 1 passed
```

## Operational Drill Status (Staging)

Alert simulation was attempted locally and blocked by missing Prometheus stack:

```bash
bash scripts/ci/phase4_alert_simulation.sh
# ERROR: Prometheus is not reachable at http://localhost:9090
```

Remaining closure for Phase 7 item 96:
- Run staging S3 fault drill with observability stack up
- Capture `BotCheckTTSCacheFallbackRateHigh` firing evidence and recovery evidence
- Attach screenshots/log excerpts to this folder

## Deferred Item Status Update

- Resolved in Phase 5 item 76:
  `services/judge/tests/test_cache_worker.py::test_warm_tts_cache_branching_scenario_precaches_all_harness_arms`
  now verifies all harness branch arms are pre-warmed (including unexecuted branches).
