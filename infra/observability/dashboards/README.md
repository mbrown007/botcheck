# BotCheck Grafana Dashboard Pack

This folder contains importable Grafana dashboards for BotCheck metrics.

## Dashboards

1. `botcheck-executive-overview.json`
- Audience: product + operations.
- Focus: run volume, success ratio, API availability, judge health, queue lag, SIP dispatch outcomes.

2. `botcheck-voice-quality.json`
- Audience: QA + voice engineering.
- Focus: deterministic voice gates (response gap, interruption recovery, turn-taking), fail/warn trends, breach breakdowns.

3. `botcheck-delivery-ops.json`
- Audience: on-call + platform engineering.
- Focus: scheduled execution pressure, callback reliability, final ACK hardening, queue lag, scrape health (including LiveKit target).

4. `botcheck-run-tracing.json`
- Audience: on-call + platform engineering.
- Focus: trace-first investigation workflow using Prometheus hotspot panels plus Tempo drilldown recipes and correlation fields.

5. `botcheck-grai-evals.json`
- Audience: QA + platform engineering.
- Focus: grai import health, eval run outcomes, dispatch latency, assertion outcomes, artifact upload health, and report assembly performance.

## Import

1. In Grafana, go to **Dashboards -> New -> Import**.
2. Upload one of the JSON files from this directory.
3. Map `DS_PROMETHEUS` to your Grafana Cloud Prometheus data source.
4. Repeat for each dashboard.

`botcheck-run-tracing.json` does not require a Tempo datasource variable. It is
deliberately Prometheus-backed and hands off to Grafana Explore / Tempo through
the documented TraceQL recipes.

## Notes

- Panels use your current metric names from `api`, `judge`, and `agent` services.
- LiveKit panels currently use scrape-health (`up{service="livekit"}`) so you can detect collection outages immediately.
- If you later expose native LiveKit OTEL/Prometheus series (room/participant/audio metrics), extend the Delivery dashboard with those signals in the same row.
- `botcheck-run-tracing.json` is intentionally hybrid: it uses Prometheus panels to find the bad window, then hands off to Tempo via the documented TraceQL recipes.
