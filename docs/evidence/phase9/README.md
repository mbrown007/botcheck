# Phase 9 Evidence

Store Scenario Packs sign-off evidence in this directory.

## Capacity Drill

Run:

```bash
BOTCHECK_PACK_ID=<pack_id> \
BOTCHECK_USER_TOKEN=<token> \
BOTCHECK_EXPECT_MAX_RUNNING=5 \
BOTCHECK_PACK_EXPECT_TOTAL_SCENARIOS=100 \
BOTCHECK_PACK_DRILL_EVIDENCE_DIR=docs/evidence/phase9/<window>/pack-capacity \
make test-pack-capacity-drill
```

Expected artifacts under `docs/evidence/phase9/<window>/pack-capacity/`:

1. `pack_capacity_summary_<pack_run_id>.json`
2. `pack_capacity_detail_<pack_run_id>.json`
3. `pack_capacity_children_<pack_run_id>.json`
4. `pack_capacity_trace_<pack_run_id>.tsv`

The summary JSON is the sign-off source for:

1. Peak running children (`peak_running <= expected_max_running`)
2. Pack size assertion (`total_scenarios == expected_total_scenarios`, when configured)
3. Deterministic terminal accounting (`completed == total_scenarios` for non-cancelled runs)

## Trigger Latency Probe

Run:

```bash
BOTCHECK_PACK_ID=<pack_id> \
BOTCHECK_USER_TOKEN=<token> \
BOTCHECK_PACK_TRIGGER_SAMPLES=5 \
BOTCHECK_PACK_TRIGGER_MAX_MS=500 \
BOTCHECK_PACK_TRIGGER_EVIDENCE_DIR=docs/evidence/phase9/<window>/pack-trigger-latency \
make test-pack-trigger-latency
```

Expected artifacts under `docs/evidence/phase9/<window>/pack-trigger-latency/`:

1. `pack_trigger_latency_samples.txt`
2. `pack_trigger_latency_summary.json`

The latency summary is the sign-off source for the pack trigger API budget check.
