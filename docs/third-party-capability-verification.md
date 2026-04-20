# Third-Party Capability Verification

This process controls how BotCheck makes architecture decisions based on external platform claims.

## Policy

1. External claims are directional until verified.
2. Any decision to `adopt` a third-party capability requires:
   - dated source evidence, and
   - hands-on POC evidence in-repo.
3. Verification must be re-run before `review_due_on`.
4. Expired or unverified claims must not drive roadmap commitments.

## Registry

Record claims in [`third_party_capabilities.yaml`](./third_party_capabilities.yaml).

Schema highlights:

- `claim_id`: stable id (`TP-YYYY-NNN` recommended)
- `provider`: platform/vendor name
- `capability`: exact feature being evaluated
- `decision`: `adopt | defer | reject`
- `source`: URL + publish/access dates
- `verification`: `method`, `verified_on`, `owner`, optional `poc_ref`
- `review_due_on`: mandatory re-verification date
- `adr_refs`: required for `adopt` decisions

## Required Evidence for Adopt Decisions

For `decision: adopt`, include:

1. `verification.method` = `poc` or `docs+poc`
2. `verification.poc_ref` path to a reproducible POC note
3. at least one ADR path in `adr_refs`

## CI Enforcement

CI validates this contract via:

`scripts/ci/validate_third_party_capabilities.py`

Failure cases:

- missing registry file
- expired `review_due_on`
- `adopt` without POC evidence
- missing referenced `poc_ref` or ADR files
- invalid date ordering (for example verified before accessed)

## Example Entry

```yaml
version: "1.0"
claims:
  - claim_id: TP-2026-001
    provider: livekit
    capability: "OpenTelemetry metrics export for RTC/SIP workloads"
    decision: defer
    status: monitoring
    source:
      url: "https://docs.livekit.io"
      title: "LiveKit Observability Docs"
      published_on: 2025-10-01
      accessed_on: 2026-02-27
    verification:
      method: docs
      verified_on: 2026-02-27
      owner: platform
      notes: "POC scheduled in Phase 4 observability work."
    review_due_on: 2026-05-30
    adr_refs: []
```
