# Grai Eval Examples

This directory contains importable `Grai Evals` example suites.

These files are **promptfoo-style YAML import fixtures** for the Grai importer,
not BotCheck graph scenarios. Do not load them through the scenario DSL.

## Import

Use the UI at `/grai-evals`, or import by API:

```bash
curl -X POST http://localhost:7700/grai/suites/import \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $BOTCHECK_TOKEN" \
  -d @- <<'JSON'
{
  "yaml_content": "REPLACE_WITH_FILE_CONTENTS"
}
JSON
```

## Current examples

- `billing-support-smoke.promptfoo.yaml`
  - Small deterministic import fixture
  - Uses only supported first-pass assertion types
  - Good first suite to import and inspect in the Grai UI
- `monitoring-assistant-targeted-tasks.promptfoo.yaml`
  - Monitoring assistant task suite derived from the upstream dashboard/anomaly/query/incident/runbook eval dataset
  - Uses deterministic assertions only, so it can run immediately against a direct HTTP transport profile
  - Demonstrates per-case `metadata.http_request_context` for iframe-style `dashboard_context` and `selected_context`
  - Good baseline for local Grafana assistant development before richer judge-based grading
- `monitoring-assistant-alert-investigations.promptfoo.yaml`
  - Alert-led incident suite focused on active alerts, latency spikes, error spread, logs, containment, and rollback decisions
  - Uses richer iframe-style context objects per case so evaluations resemble the embedded Grafana assistant more closely
  - Good follow-on suite once the baseline targeted-task coverage is stable
