# Phase 5 SIP Branching Sign-off Checklist

Use this checklist to close backlog item 76 manual SIP evidence.

## Run Metadata

- Date:
- Environment:
- Operator:
- API URL:
- SIP trunk ID:
- Scenario ID:
- Run A ID:
- Run B ID:

## Preconditions

- [ ] Scenario contains at least one branching turn with two distinct outcomes.
- [ ] `enable_branching_graph=true` in the harness runtime.
- [ ] Run Detail UI is reachable for both runs.

## Live Path Verification

### Path A (live SIP)

- [ ] Triggered run over SIP and captured Run ID.
- [ ] Branch decision selected condition: `________________`.
- [ ] Run Detail transcript renders matching taken path.
- [ ] Branch annotation shown inline between transcript turns.
- [ ] Collapsed "not taken" branch arms are visible and accurate.

### Path B (live SIP, different branch)

- [ ] Triggered second run over SIP and captured Run ID.
- [ ] Branch decision selected condition: `________________`.
- [ ] Path differs from Path A.
- [ ] Run Detail transcript renders matching taken path.
- [ ] Branch annotation shown inline between transcript turns.
- [ ] Collapsed "not taken" branch arms are visible and accurate.

## Consistency Checks

- [ ] API run events include `turn_executed` with (`turn_id`, `visit`, `turn_number`) for both runs.
- [ ] API run events include `branch_decision` with redacted snippet for both runs.
- [ ] Judge payload for each run includes non-empty `taken_path_steps`.
- [ ] Gate result and summary are present for both runs.

## Evidence Attachments

- [ ] Screenshot: Run A path rendering.
- [ ] Screenshot: Run B path rendering.
- [ ] JSON excerpt: Run A `events` branch decision detail.
- [ ] JSON excerpt: Run B `events` branch decision detail.
- [ ] Optional call recordings linked (if retention policy allows).

## Sign-off

- [ ] I confirm two distinct live SIP branch paths were executed and UI rendering matched the recorded path metadata.

Signed by:
- Name:
- Date:
