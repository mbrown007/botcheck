# Pack Capacity Drill

Validate that pack fan-out respects SIP slot limits during dispatch.

## Purpose

This drill triggers a pack run and polls child item state to verify peak concurrent
`running` children does not exceed the configured slot ceiling.

Use this before Phase 9 sign-off and after changes to:
- SIP capacity settings
- pack dispatcher behavior
- scheduler or run creation paths

## Prerequisites

- Services running (`make up` or equivalent)
- A pack with SIP scenarios prepared
- A valid user token with access to trigger pack runs

## Environment Variables

- `BOTCHECK_PACK_ID`: target pack id
- `BOTCHECK_USER_TOKEN`: bearer token for run trigger + read APIs
- `BOTCHECK_API_URL` (optional, default `http://localhost:7700`)
- `BOTCHECK_EXPECT_MAX_RUNNING` (optional, default `5`)
- `BOTCHECK_PACK_EXPECT_TOTAL_SCENARIOS` (optional, asserts `total_scenarios`)
- `BOTCHECK_PACK_EXPECT_TERMINAL_STATES` (optional, default `complete,partial,failed`)
- `BOTCHECK_PACK_DRILL_EVIDENCE_DIR` (optional, writes summary/detail/trace artifacts)
- `BOTCHECK_PACK_DRILL_TIMEOUT_S` (optional, default `900`)
- `BOTCHECK_PACK_DRILL_POLL_S` (optional, default `5`)

## Run via Make

```bash
BOTCHECK_PACK_ID=pack_abc123 \
BOTCHECK_USER_TOKEN=eyJ... \
BOTCHECK_EXPECT_MAX_RUNNING=5 \
BOTCHECK_PACK_EXPECT_TOTAL_SCENARIOS=100 \
BOTCHECK_PACK_DRILL_EVIDENCE_DIR=docs/evidence/phase9/$(date +%Y%m%d)-pack-capacity \
make test-pack-capacity-drill
```

## Run Script Directly

```bash
BOTCHECK_PACK_ID=pack_abc123 \
BOTCHECK_USER_TOKEN=eyJ... \
BOTCHECK_PACK_EXPECT_TOTAL_SCENARIOS=100 \
bash scripts/ci/pack_capacity_drill.sh
```

## Pass Criteria

- Drill exits `0`
- Reported `peak_running` is less than or equal to `BOTCHECK_EXPECT_MAX_RUNNING`
- Pack run reaches an allowed terminal state (`BOTCHECK_PACK_EXPECT_TERMINAL_STATES`)
- For non-cancelled terminal states, `completed == total_scenarios` and in-flight children are `0`

## Evidence Artifacts

When `BOTCHECK_PACK_DRILL_EVIDENCE_DIR` is set, the script writes:
- `pack_capacity_summary_<pack_run_id>.json`
- `pack_capacity_detail_<pack_run_id>.json`
- `pack_capacity_children_<pack_run_id>.json`
- `pack_capacity_trace_<pack_run_id>.tsv`

## Failure Handling

- If `peak_running` exceeds expected max:
  - Verify `MAX_CONCURRENT_OUTBOUND_CALLS` configuration
  - Inspect dispatch logs for parallel slot-acquire regressions
- If timeout is reached:
  - Check queue health (`arq:scheduler`) and worker logs
  - Verify SIP dispatch dependencies are healthy
