# Monitoring & Observability

BotCheck uses two observability paths on purpose:

1. **Prometheus** is the authoritative local/dev metrics + alerting stack.
2. **Grafana Alloy** is always the OTLP trace collector boundary and can also be
   promoted to the authoritative metrics scraper/remote-writer when
   `METRICS_STACK=alloy`.

## Architecture

1. **Services** (API, Judge, Agent) expose Prometheus-formatted metrics on their respective ports.
2. **LiveKit** exposes metrics on `:6789/metrics` (`prometheus_port`).
3. **Prometheus** scrapes the local metrics targets every 15s for dashboards and alert rules in local/dev.
4. **Grafana Alloy** always receives OTLP traces and, when `METRICS_STACK=alloy`, also scrapes metrics and forwards them to Grafana Cloud Prometheus.

## Stack Authority

### Local / dev

- `METRICS_STACK=prometheus` is the default.
- Prometheus is authoritative for metric queries, dashboards, and alert rule validation.
- Alloy runs in traces-only mode so the same targets are not scraped twice by default.

### Remote-write / Grafana Cloud validation

- Set `METRICS_STACK=alloy` when you want Alloy to be the authoritative metric scraper and Prometheus remote-write path for that environment.
- Keep Prometheus for local inspection if useful, but treat Grafana Cloud as the source of truth in that mode.

## Setup (Grafana Cloud)

1. Sign up for a free account at [grafana.com](https://grafana.com/).
2. In your Cloud Portal, find the **Prometheus** section and click **Send Metrics**.
3. Copy the following values to your `.env` file:
   - `GRAFANA_CLOUD_URL`: The Remote Write endpoint.
   - `GRAFANA_CLOUD_USER`: Your Username / Instance ID.
   - `GRAFANA_CLOUD_TOKEN`: An API Token (Access Policy) with `metrics:push` scope.
   - `GRAFANA_CLOUD_TEMPO_ENDPOINT`: Tempo OTLP endpoint in `host:port` format.
   - `GRAFANA_CLOUD_TEMPO_USER`: Tempo basic-auth username / instance ID.
   - `GRAFANA_CLOUD_TEMPO_TOKEN`: API token with `traces:write` scope.

## Scraping Targets

| Service | Address | Metrics Port |
|---|---|---|
| API | `api:8000` | 8000 (Internal) |
| Judge | `judge:9101` | 9101 |
| Agent | `agent:9102` | 9102 |
| LiveKit | `livekit:6789` | 6789 |

## Key Metrics to Watch

- `botcheck_runs_created_total`: Total test runs triggered.
- `botcheck_judge_enqueue_total`: Queue health for the scoring engine.
- `botcheck_voice_quality_p95_response_gap_milliseconds` (Gauge): Latest computed p95 TTFW in milliseconds from harness stop to bot first word.
- `botcheck_schedule_consecutive_failures{schedule_id,target_type}`: Current failure streak per schedule.
- `botcheck_schedule_run_outcomes_total{schedule_id,target_type,outcome}`: Terminal scheduled-run outcomes, used for schedule-level recency alerts.
- `botcheck_grai_eval_import_total{outcome}`: Promptfoo import success vs compile/conflict/error outcomes for Grai suites.
- `botcheck_grai_eval_runs_total{outcome}`: Terminal Grai eval worker outcomes. `failed` means assertions failed; `error` means worker/runtime failure.
- `botcheck_grai_eval_assertions_total{assertion_type,outcome}`: Per-assertion evaluation outcomes by type.
- `botcheck_grai_eval_artifact_upload_total{outcome}`: Raw request/response artifact upload outcomes (`success`, `error`, `skipped`).
- `livekit_room_active_total`: Number of concurrent test rooms.
- `botcheck_ai_caller_reply_latency_seconds{scenario_kind="ai"}`: End-to-end bot-turn-end -> caller-utterance-start latency for live AI scenarios.
- `botcheck_ai_caller_llm_request_start_gap_seconds{scenario_kind="ai"}`: Bot-turn-end -> caller-LLM-request-start latency for live AI scenarios.
- `botcheck_ai_caller_decision_to_playback_start_gap_seconds{scenario_kind="ai"}`: Caller-decision-ready -> playback-start latency for live AI scenarios.
- `botcheck_ai_voice_speculative_plans_total{outcome,scenario_kind="ai"}`: Preview-driven speculative planning outcomes (`started`, `committed`, `discarded`, `cancelled`, `error`).
- `botcheck_ai_voice_fast_ack_total{source,opening_strategy,scenario_kind="ai"}`: Fast-ack fallbacks by source (`dataset_input`, `heuristic`).
- `botcheck_ai_voice_early_playback_total{outcome,scenario_kind="ai"}`: Early playback outcomes (`started`, `committed`, `stale_suppressed`, `cancelled`, `error`).
- `botcheck_stt_listen_latency_seconds{result="speech",scenario_kind="ai"}`: AI-segmented harness speech-path STT turn-ready latency for spoken bot turns.
- `botcheck_tts_first_byte_latency_seconds{scenario_kind="ai"}`: AI-segmented harness live TTS provider time-to-first-audio for caller utterances.
- `botcheck_tts_stream_duration_seconds{scenario_kind="ai"}`: AI-segmented harness live TTS first-frame -> final-frame streaming duration.

## Dashboard Pack

Import-ready Grafana dashboards are provided in:

- `infra/observability/dashboards/botcheck-executive-overview.json`
- `infra/observability/dashboards/botcheck-voice-quality.json`
- `infra/observability/dashboards/botcheck-delivery-ops.json`
- `infra/observability/dashboards/botcheck-run-tracing.json`
- `infra/observability/dashboards/botcheck-grai-evals.json`

Import flow:

1. Grafana -> Dashboards -> New -> Import
2. Upload a dashboard JSON from `infra/observability/dashboards`
3. Map `DS_PROMETHEUS` to your Grafana Cloud Prometheus datasource

The dashboards are designed for different operators:

1. Executive Overview: intake/success/reliability at a glance
2. Voice Quality Deep Dive: deterministic timing and gate quality trends
3. Delivery & Operations: scheduler/SIP/callback pressure, final ACK health, scrape health
4. Run Tracing: trace-first investigation using Prometheus hotspots plus Tempo drilldowns
5. Grai Evals: import, execution, assertion, artifact, and report assembly health

Note: the Delivery dashboard includes `up{service="livekit"}` so you can detect LiveKit scrape outages even before native LiveKit series are fully available in your environment.

## Schedule Alerting Decision

BotCheck alerts on scheduled-run reliability at the **schedule** level, not the
run level.

- `schedule_id` is accepted metric cardinality because it is bounded by active schedules and is operationally actionable.
- `run_id` is intentionally excluded from Prometheus metrics because it is unbounded cardinality.
- When an alert fires, use the schedule's recent-run history in the product/UI to identify the exact failed run(s).

The canonical “retry policy exhausted” alert requires both:

1. failure streak state: `botcheck_schedule_consecutive_failures >= 2`
2. recency: at least two `failed|error` scheduled-run outcomes for that same `schedule_id` in the last `15m`

## Phase 4 SLO Alerts

Prometheus rule file: `infra/observability/alerts/botcheck.rules.yml`

1. `BotCheckAPIAvailabilityLow` — non-5xx request ratio `< 99%` over 10m.
2. `BotCheckRunSuccessRateLow` — completed/terminal run ratio `< 95%` over 30m.
3. `BotCheckJudgeLatencyP95High` — judge p95 duration `> 20s`.
4. `BotCheckJudgeQueueLagHigh` — enqueue-vs-processed delta `> 5` over 15m.
5. `BotCheckSIPDispatchFailures` — at least one SIP dispatch error in 15m.
6. `BotCheckSIPTelephonyDown` — `>=3` SIP dispatch errors and `0` SIP dispatch successes in 15m (sustained 5m), indicating likely trunk/provider outage.
7. `BotCheckAIBotToCallerReplyLatencyP95High` — AI caller reply p95 `> 1.7s` over 15m.
8. `BotCheckAIBotToCallerReplyLatencyP95Critical` — AI caller reply p95 `> 2.5s` over 15m; this breaches the Phase 17 staging gate.
9. `BotCheckHarnessTTSFirstByteLatencyP95High` — harness live TTS first-byte p95 `> 500ms`.
10. `BotCheckHarnessSTTListenLatencyP95High` — harness STT listen p95 for spoken turns `> 500ms`.
11. `BotCheckGraiEvalWorkerInternalErrors` — Grai eval worker hit one or more internal `error` terminal states in 15m.

## Phase 17 AI Reply Gate and Speech-Path Proxies

Use these budgets for live AI caller staging acceptance:

1. `bot turn end -> caller audible reply` p95 `<= 2500ms` hard gate, target `<= 1700ms`
2. Harness STT spoken-turn latency proxy p95 `<= 500ms`
3. Harness live TTS first-byte latency proxy p95 `<= 500ms`

All six queries below are AI-specific; `scenario_kind` is a first-class label
on all harness speech-path metrics.

Primary PromQL checks:

```promql
histogram_quantile(0.95, sum by (le) (rate(botcheck_ai_caller_reply_latency_seconds_bucket{scenario_kind="ai"}[15m])))
histogram_quantile(0.95, sum by (le) (rate(botcheck_ai_caller_llm_request_start_gap_seconds_bucket{scenario_kind="ai"}[15m])))
histogram_quantile(0.95, sum by (le) (rate(botcheck_ai_caller_decision_to_playback_start_gap_seconds_bucket{scenario_kind="ai"}[15m])))
histogram_quantile(0.95, sum by (le) (rate(botcheck_stt_listen_latency_seconds_bucket{result="speech",scenario_kind="ai"}[15m])))
histogram_quantile(0.95, sum by (le) (rate(botcheck_tts_first_byte_latency_seconds_bucket{scenario_kind="ai"}[15m])))
histogram_quantile(0.95, sum by (le) (rate(botcheck_tts_stream_duration_seconds_bucket{scenario_kind="ai"}[15m])))
```

## Phase 40 Live Lane Benchmarking

Use the Voice Quality dashboard plus the Phase 40 evidence scripts together:

1. run one lane with [ai_voice_latency_probe.sh](../scripts/ci/ai_voice_latency_probe.sh)
2. save the lane bundle under [docs/evidence/phase40](../docs/evidence/phase40/README.md)
3. compare bundles with [ai_voice_latency_compare.sh](../scripts/ci/ai_voice_latency_compare.sh)

Live PromQL checks for overlap behavior:

```promql
sum(increase(botcheck_ai_voice_fast_ack_total{scenario_kind="ai"}[1h]))
sum(increase(botcheck_ai_voice_early_playback_total{scenario_kind="ai",outcome="committed"}[1h]))
sum(increase(botcheck_ai_voice_early_playback_total{scenario_kind="ai",outcome="stale_suppressed"}[1h]))
sum(increase(botcheck_ai_voice_speculative_plans_total{scenario_kind="ai",outcome="committed"}[1h]))
```

Interpretation:

1. `fast_ack_total` should remain near zero in the shared-path lane and rise in the overlap lane.
2. `early_playback committed` should only appear when early playback is enabled.
3. `stale_suppressed` should stay low. If it climbs, the preview/final transcript match is too optimistic for that lane.
4. Pair these live signals with the offline decision matrix before changing the default runtime mode.

Verify rules are loaded:

```bash
curl -fsS http://localhost:9090/api/v1/rules | jq -r '.data.groups[].rules[].name' | grep BotCheck
```

Run full launch-readiness checks (includes rule-load validation):

```bash
make test-release-readiness-gate
```

## Local Debugging

You can view the Alloy status dashboard at [http://localhost:12345](http://localhost:12345) to verify that scraping is working and that the connection to Grafana Cloud is established.

To verify remote write from inside the Docker network:

```bash
docker compose exec -T api python - <<'PY'
import urllib.request
metrics = urllib.request.urlopen("http://alloy:12345/metrics", timeout=10).read().decode()
for line in metrics.splitlines():
    if line.startswith("prometheus_remote_storage_samples_in_total") or line.startswith("prometheus_remote_storage_samples_failed_total"):
        print(line)
PY
```

Expected:
1. `prometheus_remote_storage_samples_in_total` increases over time.
2. `prometheus_remote_storage_samples_failed_total` remains `0`.

## Tempo Traces (OTLP)

Alloy exposes OTLP receivers:

1. `alloy:4317` (gRPC)
2. `alloy:4318` (HTTP/protobuf)

`livekit` and `sip` are configured to emit OTLP traces to Alloy via:

1. `OTEL_EXPORTER_OTLP_ENDPOINT=http://alloy:4318`
2. `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`

Verify trace export counters from inside the Docker network:

```bash
docker compose exec -T api python - <<'PY'
import urllib.request
metrics = urllib.request.urlopen("http://alloy:12345/metrics", timeout=10).read().decode()
for line in metrics.splitlines():
    if (
        "otelcol_exporter_queue_capacity" in line
        and "grafana_cloud_tempo" in line
        and "data_type=\"traces\"" in line
    ) or "otelcol_exporter_sent_spans" in line or "otelcol_exporter_send_failed_spans" in line:
        print(line)
PY
```

Expected:
1. `otelcol_exporter_queue_capacity{...,data_type="traces"}` is present (pipeline loaded).
2. `otelcol_exporter_sent_spans` increases during call/test traffic.
3. `otelcol_exporter_send_failed_spans` remains at `0`.

### Hosted Tempo validation

After local counters confirm export is healthy:

1. open Grafana Cloud -> Explore -> Tempo
2. use the same time window as the local test traffic
3. run `{ name = "run.lifecycle" }`
4. confirm one trace spans API -> harness -> judge for a normal manual run

If local exporter counters are healthy but hosted Tempo is empty, treat that as
an Alloy/cloud delivery problem rather than an application instrumentation bug.

## Trace Investigation Workflows

BotCheck currently uses the default OpenTelemetry SDK sampling policy:

- parent-based always-on in API, agent, and judge
- no Alloy tail-sampling policy yet

That means traces should be complete by default, but storage cost controls have
not yet moved into the collector.

### Core TraceQL searches

Paste these into Grafana Explore -> Tempo:

```traceql
{ name = "run.lifecycle" }
{ name = "run.lifecycle" && trigger.source = "scheduled" }
{ name = "dispatch.sip" }
{ name = "harness.session" && transport.kind = "http" }
{ name = "judge.run" }
```

### Correlation fields

Use the same stable fields across traces, logs, and Prometheus-driven incident
triage:

- `run.id`
- `tenant.id`
- `scenario.kind`
- `trigger.source`
- `schedule.id`
- `transport.kind`
- `transport_profile.id`
- `trace_id`
- `span_id`

### Local trace-to-log pivot

Loki shipping is not yet part of the BotCheck local stack, so the local/dev
trace-to-log pivot is:

```bash
# Replace <run_id> and <trace_id> with the actual IDs from the Tempo trace view.
docker compose logs api | rg '<run_id>|<trace_id>'
docker compose logs agent | rg '<run_id>|<trace_id>'
docker compose logs judge | rg '<run_id>|<trace_id>'
```

Use the run/schedule IDs from the trace attributes to narrow the log search.

### Dashboard handoff

Import [botcheck-run-tracing.json](/home/marc/Documents/github/botcheck/infra/observability/dashboards/botcheck-run-tracing.json) for the trace investigation workflow:

1. identify the bad time window with Prometheus hotspot panels
2. open Grafana Explore / Tempo
3. paste the matching TraceQL recipe
4. pivot to logs with `run.id` or `trace_id` if the trace shows a failure boundary
