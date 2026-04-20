# Pack Trigger Latency Probe

Validate `POST /packs/{id}/run` response latency remains within the expected API budget.

## Purpose

This probe samples manual pack trigger requests and enforces a millisecond threshold.
Use it to validate the non-blocking `202` behavior before Phase 9 sign-off and after
pack dispatch path changes.

## Prerequisites

- API service running
- Existing pack ID
- User token with pack trigger access

## Environment Variables

- `BOTCHECK_PACK_ID` (required)
- `BOTCHECK_USER_TOKEN` (required)
- `BOTCHECK_API_URL` (optional, default `http://localhost:7700`)
- `BOTCHECK_PACK_TRIGGER_SAMPLES` (optional, default `3`)
- `BOTCHECK_PACK_TRIGGER_MAX_MS` (optional, default `500`)
- `BOTCHECK_PACK_TRIGGER_CANCEL_AFTER` (optional, default `true`)
- `BOTCHECK_PACK_TRIGGER_EVIDENCE_DIR` (optional)

## Run via Make

```bash
BOTCHECK_PACK_ID=pack_abc123 \
BOTCHECK_USER_TOKEN=eyJ... \
BOTCHECK_PACK_TRIGGER_SAMPLES=5 \
BOTCHECK_PACK_TRIGGER_MAX_MS=500 \
BOTCHECK_PACK_TRIGGER_EVIDENCE_DIR=docs/evidence/phase9/$(date +%Y%m%d)-pack-trigger-latency \
make test-pack-trigger-latency
```

## Pass Criteria

1. Script exits `0`
2. Every sampled request returns HTTP `202`
3. Observed max latency (`max_observed_ms`) is less than or equal to `BOTCHECK_PACK_TRIGGER_MAX_MS`

## Evidence Artifacts

When `BOTCHECK_PACK_TRIGGER_EVIDENCE_DIR` is set, the probe writes:

1. `pack_trigger_latency_samples.txt`
2. `pack_trigger_latency_summary.json`
