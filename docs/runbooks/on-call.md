# BotCheck On-Call Runbook (Phase 4)

Last Updated: 2026-03-04

This runbook is for production/staging alerts tied to BotCheck launch-readiness SLOs.
Set `API_URL` to your deployment API base URL before running command snippets
(example: `export API_URL=http://localhost:7700` in local dev).

## 1. Alert Routing

1. Route `severity=critical` alerts to PagerDuty primary on-call immediately.
2. Route `severity=warning` alerts to Slack `#botcheck-alerts` with 15-minute triage SLA.
3. Escalate to secondary on-call after 10 minutes for unanswered critical pages.

## 2. Core Alerts and First Actions

## `BotCheckAPIAvailabilityLow`

1. Check API health and metrics:
   - `curl -fsS "${API_URL%/}/health"`
   - `curl -fsS "${API_URL%/}/metrics" | head`
2. Check API logs for 5xx bursts:
   - `docker compose logs --since=15m api`
3. If caused by deploy/migration mismatch, roll back app container and re-run migrations.

## `BotCheckRunSuccessRateLow`

1. Identify dominant terminal failure mode:
   - `botcheck_run_state_transitions_total{to_state=~"failed|error"}`
2. Correlate with API failure counters:
   - `botcheck_run_failures_total`
3. If concentrated on scheduled traffic, validate scheduler dispatch and SIP capacity.

## `BotCheckJudgeLatencyP95High`

1. Check judge in-flight and duration trends:
   - `botcheck_judge_runs_inflight`
   - `botcheck_judge_run_duration_seconds_*`
2. Check Anthropic/API upstream health and rate limits in judge logs.
3. If sustained, reduce concurrency or scale judge workers before backlog grows.

## `BotCheckJudgeQueueLagHigh`

1. Compare enqueue vs processed trend:
   - `botcheck_judge_enqueue_total{outcome="success"}`
   - `botcheck_judge_runs_total`
2. Confirm Redis and ARQ worker health.
3. Drain backlog before resuming high-frequency schedules.

## `BotCheckSIPTelephonyDown`

1. Confirm dispatch collapse pattern:
   - `increase(botcheck_sip_dispatch_total{outcome="error"}[15m])`
   - `increase(botcheck_sip_dispatch_total{outcome="success"}[15m])`
2. Check `api` logs for SIP dispatch/auth failures:
   - `docker compose logs --since=15m api | grep -E "SIP dispatch failed|401|403|407|trunk|telephony" -i`
3. Validate SIP bridge/trunk health:
   - container mode: `docker compose ps sip && docker compose logs --since=15m sip`
   - native mode: check `livekit-sip` service status/logs and trunk registration/auth state.
4. Trigger one controlled outbound smoke run after remediation and confirm dispatch success before closing.

## `BotCheckBranchClassifierTimeoutRateHigh`

1. Confirm timeout ratio and volume:
   - `sum(increase(botcheck_branch_classifier_calls_total{outcome="timeout"}[10m]))`
   - `sum(increase(botcheck_branch_classifier_calls_total[10m]))`
2. Check harness agent logs for timeout/error spikes:
   - `docker compose logs --since=15m agent | grep -E "branch_classifier\\.timeout|branch_classifier\\.error" -i`
3. Validate classifier settings (`BRANCH_CLASSIFIER_MODEL`, `BRANCH_CLASSIFIER_TIMEOUT_S`) and upstream model health.
4. Until resolved, treat branch routing as degraded because runs are falling back to `"default"` paths.

## `BotCheckRunHeartbeatStaleRateHigh`

1. Confirm stale-heartbeat trend:
   - `sum(increase(botcheck_run_reaper_actions_total{outcome="heartbeat_stale"}[15m]))`
   - `sum(increase(botcheck_run_reaper_actions_total{outcome="closed"}[15m]))`
2. Spot-check active runs for heartbeat recency context:
   - `docker compose logs --since=15m api | grep -E "run_heartbeat_received|run_reaped_" -i`
3. Validate harness->API callback path health (network, DNS, auth secret drift):
   - `docker compose logs --since=15m agent | grep -E "run_heartbeat_send_failed|heartbeat" -i`
4. If stale heartbeats are rising but runs are not overdue, treat as degraded signaling and open a warning incident. If overdue closures start rising, escalate to critical.

## `BotCheckHeartbeatCallbackErrorRateHigh`

1. Confirm callback error ratio and volume:
   - `sum(increase(botcheck_agent_api_callbacks_total{endpoint="heartbeat",outcome="error"}[10m]))`
   - `sum(increase(botcheck_agent_api_callbacks_total{endpoint="heartbeat"}[10m]))`
2. Check harness logs for callback failures:
   - `docker compose logs --since=15m agent | grep -E "run_heartbeat_send_failed|/heartbeat|401|403|5.." -i`
3. Check API logs for heartbeat endpoint failures:
   - `docker compose logs --since=15m api | grep -E "/runs/.*/heartbeat|invalid_state|403|404|5.." -i`
4. Validate `HARNESS_SECRET` parity across `agent` and `api` deployments and confirm no recent secret rotation drift.

## `BotCheckProviderCircuitOpen`

1. Confirm which circuit is open and how long it has persisted:
   - `max by (source,provider,service,component) (botcheck_provider_circuit_state{state="open"})`
   - `sum by (source,component) (botcheck_provider_circuit_rejections_total)`
2. Cross-check degraded projection from API:
   - `curl -fsS "${API_URL%/}/features" | jq '.provider_degraded, .provider_circuits'`
3. Inspect service logs for transition/rejection context:
   - API preview path: `docker compose logs --since=15m api | grep -E "provider_circuit_(transition|rejected)" -i`
   - Harness path: `docker compose logs --since=15m agent | grep -E "provider_circuit_(transition|rejected)" -i`
   - Judge cache path: `docker compose logs --since=15m judge | grep -E "provider_circuit_(transition|rejected)" -i`
4. Remediate upstream provider outage/timeout conditions. Keep incident open until circuit returns to `closed` for two consecutive evaluation windows.

## `BotCheckProviderCircuitRejectionsHigh`

1. Confirm rejection surge by component:
   - `sum by (provider,service,component) (increase(botcheck_provider_circuit_rejections_total[10m]))`
2. Correlate with state gauge to distinguish sustained-open vs flapping behavior:
   - `max by (source,provider,service,component) (botcheck_provider_circuit_state{state="open"})`
3. If rejections are rising but circuits are frequently returning `closed`, treat as intermittent upstream instability and capture provider latency/timeout evidence from API/agent/judge logs.
4. If rejections align with sustained `open`, follow `BotCheckProviderCircuitOpen` remediation and escalate if end-user preview/cache impact is visible.

## `BotCheckAIBotToCallerReplyLatencyP95High`

1. Check the current p95 reply gap and segment breakdown:
   - `histogram_quantile(0.95, sum by (le) (rate(botcheck_ai_caller_reply_latency_ms_bucket{scenario_kind="ai"}[15m])))`
   - `# the remaining three queries are shared speech-path proxies`
   - `histogram_quantile(0.95, sum by (le) (rate(botcheck_stt_listen_latency_ms_bucket{result="speech",scenario_kind="ai"}[15m])))`
   - `histogram_quantile(0.95, sum by (le) (rate(botcheck_tts_first_byte_latency_ms_bucket{scenario_kind="ai"}[15m])))`
   - `histogram_quantile(0.95, sum by (le) (rate(botcheck_tts_stream_duration_ms_bucket{scenario_kind="ai"}[15m])))`
2. Inspect agent logs for correlated provider timeout/circuit events:
   - `docker compose logs --since=15m agent | grep -E "provider_circuit_|AI caller|branch_classifier|timeout" -i`
3. If STT is dominant, reduce endpointing/silence thresholds before changing providers.
4. If TTS first-byte is dominant, validate connection reuse, provider health, and low-latency voice model selection.

## `BotCheckAIBotToCallerReplyLatencyP95Critical`

1. Treat this as a release gate failure for staging and a production incident if user-visible.
2. Freeze AI scenario rollout/smoke validation until p95 reply latency returns below `2.5s` for two consecutive windows.
3. Prioritize the largest segment from the breakdown queries above; do not tune multiple segments blindly.

## `BotCheckHarnessTTSFirstByteLatencyP95High`

1. Confirm shared harness-path p95 first-byte latency:
   - `histogram_quantile(0.95, sum by (le) (rate(botcheck_tts_first_byte_latency_ms_bucket{scenario_kind="ai"}[15m])))`
2. Check agent logs for TTS provider degradation or circuit activity:
   - `docker compose logs --since=15m agent | grep -E "service=tts|provider_circuit_|Live TTS" -i`
3. Validate provider session reuse and selected voice model before escalating upstream.

## `BotCheckHarnessSTTListenLatencyP95High`

1. Confirm shared harness-path p95 STT listen latency for spoken turns:
   - `histogram_quantile(0.95, sum by (le) (rate(botcheck_stt_listen_latency_ms_bucket{result="speech",scenario_kind="ai"}[15m])))`
2. Check whether latency is tied to endpointing/silence settings or broad provider slowdown:
   - `docker compose logs --since=15m agent | grep -E "STT|endpointing|timeout" -i`
3. Tune endpointing and merge windows first; provider escalation is secondary unless timeouts/circuit activity are visible.

## `SIP Session Refresh / Re-INVITE Failures`

Use this section when long calls (20-30+ minutes) drop unexpectedly or carriers report timer failures.

1. Confirm call-duration drop pattern in runs and SIP metrics:
   - `botcheck_run_duration_seconds_*`
   - `botcheck_sip_call_duration_seconds_*`
   - `increase(botcheck_sip_dispatch_total{outcome="success"}[30m])`
2. Inspect SIP bridge/provider logs for `re-INVITE`, `UPDATE`, `Session-Expires`, `422`, `408`, `481`:
   - `docker compose logs --since=30m sip | grep -E "re-INVITE|UPDATE|Session-Expires|422|408|481" -i`
3. Validate trunk/session timer config on the SIP provider and `livekit-sip` deployment.
4. Run a controlled 30+ minute SIP call and archive evidence under `docs/evidence/phase6/heartbeat-sip-signaling-soak.md`.

Metric semantics note:
- `botcheck_sip_call_duration_seconds_*` records all calls where SIP joined, including runs that later fail after join.
- `botcheck_sip_call_outcomes_total{outcome="no_answer"}` does not contribute to SIP call duration because no SIP participant joined.

## 3. Incident Response Contract

1. Open incident record in `docs/incidents/production_incidents.yaml`.
2. Add timeline, scope, and remediation owner.
3. Before closure, add/update deterministic regression fixture and run:
   - `uv run python scripts/ci/validate_incident_regressions.py`
4. Link fixture/scenario ID in incident record.

## 4. Recovery Validation (before closing page)

1. `scripts/ci/release_readiness_gate.sh` passes.
2. SLO alerts recover to green for two consecutive evaluation windows.
3. One scheduled run completes and judges successfully end-to-end.

## 5. Admin Auth Recovery (Phase 6)

Use this only for operator-assisted account recovery when a user has lost TOTP
device access and cannot use recovery codes.

1. Reset 2FA (disable TOTP, invalidate all recovery codes, revoke active sessions):
   - `uv run --project services/api python services/api/scripts/admin_recovery.py --tenant-id "${TENANT_ID:-default}" --email "user@example.com" --actor-id "operator:alice" reset-2fa`
2. Reset only recovery codes (keep TOTP enabled):
   - `uv run --project services/api python services/api/scripts/admin_recovery.py --tenant-id "${TENANT_ID:-default}" --email "user@example.com" --actor-id "operator:alice" reset-recovery-codes`
3. Verify audit trail was written:
   - `curl -fsS "${API_URL%/}/audit?resource_type=user&actor_id=operator:alice" -H "Authorization: Bearer ${DEV_TOKEN:-$DEV_USER_TOKEN}"`

Notes:
- `--actor-id` is mandatory so recovery actions are attributable in `audit_log`.
- After `reset-2fa`, instruct the user to log in with password and re-enroll TOTP in User Settings.

## 6. Rejudge Completed Runs

Use this when scoring logic has changed and you need to re-run judge evaluation for an
already terminal run (`complete`, `failed`, or `error`) without re-running the call.

1. Re-enqueue a run for judging:
   - `uv run --project services/api python -m botcheck_api.admin rejudge-run --tenant-id "${TENANT_ID:-default}" --run-id "run_abc123" --actor-id "operator:alice" --reason "scoring rules updated"`
2. Confirm the run transitions back to `judging` and a `judge_reenqueued` event is present:
   - `curl -fsS "${API_URL%/}/runs/run_abc123" -H "Authorization: Bearer ${DEV_TOKEN:-$DEV_USER_TOKEN}" | jq '.state, .events[-1]'`
3. Confirm audit trail was written:
   - `curl -fsS "${API_URL%/}/audit?resource_type=run&resource_id=run_abc123&actor_id=operator:alice" -H "Authorization: Bearer ${DEV_TOKEN:-$DEV_USER_TOKEN}"`

Limitations:
- Rejudge replays stored conversation, path steps, and AI context from the original run.
- `tool_context` is not currently persisted on runs, so rejudge sends `tool_context: []`.
- Do not use rejudge for in-flight runs; the command rejects non-terminal states.
