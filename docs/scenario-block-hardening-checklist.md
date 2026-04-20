# Scenario Block Hardening Checklist

Hardening and regression focus for the next few cycles. This intentionally pauses new
block features and concentrates on proving the current block runtime is reliable across
builder, API, cache warming, and run execution.

---

## Scope

Current shipped block `kind` values (the `ScenarioBlock` discriminated union):
- `harness_prompt`
- `bot_listen`
- `hangup`
- `wait`
- `time_route`

Per-turn config knobs (fields on `TurnConfig`, not block kinds):
- `retry_on_silence`
- `listen_for_s`
- `timeout_s`

Branching modes (values of `BranchMode`, apply to `harness_prompt` and `bot_listen` only):
- `classifier` (default)
- `keyword`
- `regex`

This checklist assumes:
- no new block kinds are added until the current surface is stable
- migrated example scenarios remain the primary regression corpus
- end-to-end behavior matters more than adding more micro-features

---

## Exit Criteria

Do not start the next block feature until all of the following are true:

- builder-authored `wait` scenarios save, reload, cache warm, and run cleanly
- builder-authored `time_route` scenarios save, reload, cache warm, and run cleanly
- keyword and regex decision blocks round-trip through the builder without rule loss
- all long-lived services (`api`, `agent`, `cache-worker`, `judge`) accept the current
  block schema after a normal restart — verified manually via the smoke pass below
  (no automated startup-schema hook exists today)
- dark mode remains readable for all non-legacy block nodes
- validation failures are actionable from the builder without reading backend logs

---

## Priority Backlog

### 1. End-to-End Regression Scenarios

Add and keep a small set of canonical graph scenarios that exercise the new block system
through the real stack.

Target scenarios:
- `hangup` / `bot_listen`: bot greet -> harness prompt -> hangup (terminal-path smoke)
- `wait`: harness prompt -> wait -> harness prompt -> bot response
- `time_route`: bot greet -> time route -> day path / night path -> convergence
- `keyword branch`: deterministic IVR/menu detection without LLM classification
- `regex branch`: deterministic match on a bot phrase or reference format

For each scenario, prove:
- builder can author or edit it
- YAML save/reload is lossless
- cache rebuild completes
- run dispatch succeeds
- transcript/path matches expectation

### 2. Cache-Warming Regression Coverage

Keep growing judge/API coverage for scenario cache warming against modern block payloads.

Minimum expectations:
- `wait` does not create bogus cache work
- `time_route` payloads are accepted by cache-worker
- all cacheable harness turns behind branching/time-route structures are warmed
- cache status transitions (`warming` -> `warm` / `partial` / `cold`) remain correct

Operational note:
- stale `cache-worker` and stale `api` containers have already produced false-negative
  feature failures in local dev
- service alignment must be treated as part of hardening, not an afterthought

### 3. Builder Save / Reload / Apply Reliability

Focus on the failure modes actually encountered so far:
- generic validation banner with no actionable detail
- YAML serialization drift (`time_route` HH:MM quoting)
- node-local state not syncing back into serialized YAML
- dark-mode readability regressions for new block editors

Known code bug to fix before the round-trip criterion is met:
- `hangupNode.fromYaml` in `web/src/lib/node-registry.ts` injects `content` and
  `listen` fields that do not exist on `HangupBlock`; these extra fields survive
  round-trips only because the backend model currently ignores extras — they will
  cause a validation failure if `extra = "forbid"` is ever tightened

Target tests:
- builder save shows node-scoped validation messages for `turns.N...` API errors
- `Apply` followed by `Save` preserves `time_route` windows exactly
- branch mode/rules survive edit -> save -> reload
- block node editors remain usable in dark mode

### 4. Corpus Maintenance

The migrated example scenarios are now a real regression asset, not just sample content.

Rules:
- prefer updating the example corpus over inventing ad hoc one-off YAML
- if a live scenario exposes a bug, capture that shape in repo fixtures/tests
- keep examples in canonical block form only

---

## Manual Smoke Pass

Run this smoke pass after touching shared scenario/block code:

Preferred command:

```bash
bash scripts/smoke_block_runtime_alignment.sh \
  --user-token "$BOTCHECK_USER_TOKEN" \
  --wait-scenario-id <wait-scenario-id> \
  --time-route-scenario-id <time-route-scenario-id>
```

What it automates:
- restarts `api`, `agent`, `cache-worker`, and `judge`
- waits for `GET /health`
- rebuilds cache for one `wait` and one `time_route` scenario
- polls both scenarios until `cache_status == "warm"`

What still remains manual:
- save and run both scenarios from the builder
- check transcript ordering and selected `time_route` path
- confirm no `union_tag_invalid` errors in service logs

If you do not use the script, run the equivalent manual sequence:

1. Restart long-lived Python services:
   - `api`
   - `agent`
   - `cache-worker`
   - `judge`
2. Rebuild cache for one `wait` scenario and one `time_route` scenario.
3. Save and run both scenarios from the builder.
4. Confirm:
   - no `union_tag_invalid` errors in service logs
   - cache reaches `warm`
   - transcript ordering is correct
   - selected `time_route` path matches the configured clock window

If any of those fail, treat that as a release-blocking regression for the block runtime.

---

## Suggested Cycle Plan

### Cycle 1
- Pin `wait` and `time_route` end-to-end coverage
- Fix any remaining cache warm or builder round-trip drift

### Cycle 2
- Pin keyword/regex branch scenarios through builder save + runtime execution
- Tighten transcript/path assertions for deterministic branching

### Cycle 3
- Re-run the migrated example corpus and add tests for any real-world break found
- Re-evaluate whether the block runtime is now stable enough for the next feature

---

## Out of Scope During Hardening

Do not add these until the checklist above is boringly green:
- `assert` / `assert_on_conversation`
- any speech-in speech-out runtime work
- additional new block kinds
- broad builder redesign unrelated to reliability

The goal for the next few cycles is confidence, not surface area.
