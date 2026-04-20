# Incident Regression Workflow

Closed production incidents must be linked to deterministic regression fixtures.

## Registry

Update [`production_incidents.yaml`](./production_incidents.yaml) with one entry per incident:

```yaml
version: "1.0"
incidents:
  - id: INC-2026-0007
    source: production
    status: closed
    title: "Bot leaked internal prompt after repeated role-play pressure"
    regression_fixture_id: inverse-jailbreak-harness-hardening
```

## Required Closure Contract

For every incident where:

- `source: production`
- `status: closed`

the linked `regression_fixture_id` must reference a scenario in `scenarios/examples` that includes both tags:

- `regression-fixture`
- `incident:<incident-id-lowercase>`

CI enforces this via `scripts/ci/validate_incident_regressions.py`.
