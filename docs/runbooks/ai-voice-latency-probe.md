# AI Voice Latency Probe

Measure the Phase 40 voice-pipeline improvements using a repeatable AI scenario
probe against a live BotCheck environment.

## Purpose

This probe runs one or more AI voice scenarios through `POST /runs/`, waits for
terminal state, and summarizes the harness agent's Phase 40 metrics:

- `botcheck_ai_caller_reply_latency_seconds`
- `botcheck_ai_caller_decision_latency_seconds`
- `botcheck_ai_caller_llm_request_start_gap_seconds`
- `botcheck_ai_caller_decision_to_playback_start_gap_seconds`
- `botcheck_ai_voice_preview_events_total`
- `botcheck_ai_voice_speculative_plans_total`
- `botcheck_ai_voice_fast_ack_total`
- `botcheck_ai_voice_early_playback_total`

Use it to compare these lanes:

1. Shared-path pipeline only
2. Pipeline with overlap enabled
3. Native speech from Phase 39 when available

## Important Constraint

The metrics are process-wide on the agent instance. Run the probe in a quiet
environment, or on a dedicated harness worker, so the deltas belong to your
benchmark runs.

## Prerequisites

- API service reachable
- Harness agent metrics endpoint reachable
- Existing AI scenario ID
- Voice-capable destination or transport profile when the scenario requires one
- User token with run-create access

## Environment Variables

- `BOTCHECK_AI_SCENARIO_ID` (required)
- `BOTCHECK_USER_TOKEN` (required)
- `BOTCHECK_API_URL` (optional, default `http://localhost:7700`)
- `BOTCHECK_AGENT_METRICS_URL` (optional, default `http://localhost:9102/metrics`)
- `BOTCHECK_TRANSPORT_PROFILE_ID` (optional)
- `BOTCHECK_AI_VOICE_LATENCY_SAMPLES` (optional, default `3`)
- `BOTCHECK_AI_VOICE_LATENCY_POLL_INTERVAL_S` (optional, default `2`)
- `BOTCHECK_AI_VOICE_LATENCY_RUN_TIMEOUT_S` (optional, default `180`)
- `BOTCHECK_AI_VOICE_MODE_LABEL` (optional, default `shared_path`)
- `BOTCHECK_AI_VOICE_RETENTION_PROFILE` (optional, default `standard`)
- `BOTCHECK_AI_VOICE_EVIDENCE_DIR` (optional)

## Run Via Make

Shared-path improvements only:

```bash
BOTCHECK_AI_SCENARIO_ID=ai_scn_123 \
BOTCHECK_TRANSPORT_PROFILE_ID=dest_voice_1 \
BOTCHECK_USER_TOKEN=eyJ... \
BOTCHECK_AI_VOICE_MODE_LABEL=shared_path \
BOTCHECK_AI_VOICE_EVIDENCE_DIR=docs/evidence/phase40/$(date +%Y%m%d)-shared-path \
make test-ai-voice-latency
```

Overlap enabled:

```bash
BOTCHECK_AI_SCENARIO_ID=ai_scn_123 \
BOTCHECK_TRANSPORT_PROFILE_ID=dest_voice_1 \
BOTCHECK_USER_TOKEN=eyJ... \
BOTCHECK_AI_VOICE_MODE_LABEL=overlap_enabled \
BOTCHECK_AI_VOICE_EVIDENCE_DIR=docs/evidence/phase40/$(date +%Y%m%d)-overlap \
make test-ai-voice-latency
```

Native speech lane when Phase 39 speech runtime is available:

```bash
BOTCHECK_AI_SCENARIO_ID=ai_scn_123 \
BOTCHECK_TRANSPORT_PROFILE_ID=dest_voice_1 \
BOTCHECK_USER_TOKEN=eyJ... \
BOTCHECK_AI_VOICE_MODE_LABEL=native_speech \
BOTCHECK_AI_VOICE_EVIDENCE_DIR=docs/evidence/phase40/$(date +%Y%m%d)-native-speech \
make test-ai-voice-latency
```

## Interpreting The Summary

The probe writes `ai_voice_latency_summary.json` with:

- run-by-run terminal detail from `GET /runs/{id}`
- average latency deltas in milliseconds for the four Phase 40 histograms
- speculative / fast-ack / early-playback counter deltas

Interpretation guidance:

1. `reply_latency.avg_ms` is the operator-facing headline number.
2. `llm_request_start_gap.avg_ms` should shrink after client reuse and overlap.
3. `decision_to_playback_start_gap.avg_ms` should shrink after progressive TTS
   and early playback.
4. `fast_ack` and `early_playback` deltas should stay near zero in the
   shared-path lane and increase in the overlap lane.
5. `early_playback.stale_suppressed` must stay low. A rising number means the
   speculative transcript match is too optimistic for the tested scenario.

## Evidence Artifacts

When `BOTCHECK_AI_VOICE_EVIDENCE_DIR` is set, the probe writes:

1. `agent_metrics_before.prom`
2. `agent_metrics_after.prom`
3. `run_details.jsonl`
4. `ai_voice_latency_summary.json`

## Decision Matrix

Use the evidence bundles to compare:

- latency: `reply_latency.avg_ms`, `decision_to_playback_start_gap.avg_ms`
- transcript fidelity: run outcomes plus `stale_suppressed`
- debugging quality: richness of transcript artifacts and logs
- provider flexibility: which transports/providers support the lane
- operational complexity: number of flags, cancellation paths, and failure modes

## Build The Decision Matrix

Once you have at least two lane bundles, compare them with:

```bash
bash scripts/ci/ai_voice_latency_compare.sh \
  --bundle docs/evidence/phase40/<YYYYMMDD>-shared-path \
  --bundle docs/evidence/phase40/<YYYYMMDD>-overlap-enabled \
  --bundle docs/evidence/phase40/<YYYYMMDD>-native-speech \
  --output docs/evidence/phase40/phase40-ai-voice-decision-matrix.md \
  --json-output docs/evidence/phase40/phase40-ai-voice-decision-matrix.json
```

This produces a markdown decision matrix that summarizes:

1. per-lane latency metrics
2. fast-ack / early-playback activity
3. transcript-fidelity proxy signals
4. lane-level debugging, flexibility, and operational-complexity assessments

## Scaffold A Benchmark Window

If you want a ready-made execution plan for one benchmark session:

```bash
bash scripts/ci/ai_voice_latency_benchmark_plan.sh \
  --ai-scenario-id <ai_scenario_id> \
  --transport-profile-id <transport_profile_id> \
  --date-label "$(date +%Y%m%d)" \
  --output docs/evidence/phase40/phase40-ai-voice-plan.md
```

This prints:

1. the shared-path probe command
2. the overlap-enabled probe command
3. the optional native-speech probe command
4. the final compare command
