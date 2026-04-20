# Phase 6 Heartbeat + SIP Signaling Soak Evidence

Date:
Environment:
Operator:

## Goal

Demonstrate that:
- harness heartbeats remain healthy during live calls;
- stale-heartbeat warnings are observable and triaged;
- 30+ minute SIP calls do not drop due to session timer / re-INVITE failures.

## Test Window

- Start (UTC):
- End (UTC):
- Duration:

## Run Matrix

| Run ID | Scenario ID | Transport | Start (UTC) | End (UTC) | Duration (s) | Final state | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |

## Heartbeat Evidence

1. `run_heartbeat_received` log sample(s):
   - paste link/snippet:
2. `botcheck_run_heartbeats_total` snapshot:
   - updated:
   - duplicate_or_stale:
   - ignored_terminal:
   - invalid_state:
3. `botcheck_run_heartbeat_lag_seconds` p95/p99:
   - p95:
   - p99:

## Reaper / Staleness Evidence

1. `botcheck_run_reaper_actions_total{outcome="heartbeat_stale"}` over test window:
2. `botcheck_run_reaper_actions_total{outcome="closed"}` over test window:
3. Any forced closures:
   - run_id:
   - end_reason:
   - event detail heartbeat context (`heartbeat_stale`, `heartbeat_age_s`):

## SIP Session Timer / Re-INVITE Evidence

1. 30+ minute SIP run IDs:
2. SIP logs reviewed for session refresh messages (`re-INVITE`/`UPDATE`):
   - link/snippet:
3. Any timer negotiation failures (`422`, `408`, `481`):
   - none / details:

## Verdict

- [ ] Pass
- [ ] Needs follow-up

Follow-up actions:
- 

