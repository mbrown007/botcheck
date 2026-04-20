# Pack Examples

This directory contains curated pack payload examples for the Packs feature.
These files match the `ScenarioPackUpsert` API shape.

Use them when you want to:

- create a starter smoke pack for direct HTTP testing
- build a mixed graph-plus-AI regression pack
- give operators a copyable reference for pack item layout

## Example Index

| File | Best for | Item mix | What it demonstrates |
| --- | --- | --- | --- |
| `http-smoke-pack.json` | Fast pre-SIP smoke testing | Graph only | Small pack for direct HTTP transport profiles. |
| `ai-regression-pack.json` | Scheduled regression and red-team coverage | Graph + AI | Mixed pack items with AI scenarios and baseline graph checks. |
| `monitoring-assistant-http-pack.json` | Monitoring assistant targeted task coverage | Graph only | Dashboard, anomaly, query, incident, and runbook smoke checks for a Grafana assistant over direct HTTP. |

## Run A Pack

Create the pack first, then trigger it with a transport profile:

```bash
curl -X POST http://localhost:8000/packs/ \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  --data @scenarios/packs/examples/http-smoke-pack.json
```

```bash
curl -X POST http://localhost:8000/packs/PACK_ID/run \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  --data '{"transport_profile_id":"dest_http_smoke"}'
```

## Notes

- Packs do not embed transport config. Choose the SIP or HTTP profile when you
  run or schedule the pack.
- `ai_scenario_id` entries assume you created the matching AI scenarios first.
