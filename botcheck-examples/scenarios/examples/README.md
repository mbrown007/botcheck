# Graph Scenario Examples

This directory contains the maintained graph-scenario examples for BotCheck.
Use them as runnable references for graph authoring, SIP smoke checks, and
adversarial regression packs.

## Run Locally

Most examples use `${BOT_SIP_USER}` and `${SIP_PROVIDER}` placeholders, so set
those first before loading them through the DSL.

Validate a single example with the exact `uv run` path used by the shared DSL:

```bash
BOT_SIP_USER=ci-bot SIP_PROVIDER=ci.example.com \
UV_CACHE_DIR=/tmp/uv-cache \
uv run python -c "from botcheck_scenarios import load_scenario; s = load_scenario('scenarios/examples/golden-path-billing.yaml'); print('✓', s.name)"
```

Validate the whole examples directory:

```bash
BOT_SIP_USER=ci-bot SIP_PROVIDER=ci.example.com \
UV_CACHE_DIR=/tmp/uv-cache \
uv run python -c "from botcheck_scenarios import load_scenarios_dir; scenarios = load_scenarios_dir('scenarios/examples'); print(f'Loaded {len(scenarios)} example scenarios')"
```

If your local stack is running, you can also use the convenience Make target:

```bash
make scenario-validate f=scenarios/examples/golden-path-billing.yaml
```

## Example Index

| File | Scenario ID | Type | Dimensions | Transport | What it tests |
| --- | --- | --- | --- | --- | --- |
| `golden-path-billing.yaml` | `golden-path-billing` | `golden_path` | `routing`, `reliability` | `sip` | Happy-path billing balance request with expected routing success. |
| `routing-transfer.yaml` | `routing-transfer-billing` | `golden_path` | `routing`, `reliability` | `sip` | Billing-dispute transfer flow with explicit transfer expectation. |
| `compliance-pii-refusal.yaml` | `compliance-pii-refusal` | `compliance` | `pii_handling`, `policy`, `routing` | `sip` | PCI/PII refusal behavior for payments flows. |
| `jailbreak-dan-prompt.yaml` | `jailbreak-dan-prompt` | `adversarial` | `jailbreak`, `disclosure`, `policy` | `sip` | Multi-turn DAN jailbreak resistance and system-prompt protection. |
| `jailbreak-roleplay-persona-escape.yaml` | `jailbreak-roleplay-persona-escape` | `adversarial` | `jailbreak`, `disclosure`, `role_integrity`, `policy` | `sip` | Persona escape attacks: named persona framing, fictional character, impersonation, completion trap. |
| `jailbreak-hypothetical-framing.yaml` | `jailbreak-hypothetical-framing` | `adversarial` | `jailbreak`, `disclosure`, `policy`, `role_integrity` | `sip` | Hypothetical and fiction wrapper attacks: academic framing, story wrapper, hypothetical self-override, thought experiment. |
| `social-engineering-urgency-pressure.yaml` | `social-engineering-urgency-pressure` | `adversarial` | `jailbreak`, `policy`, `pii_handling`, `role_integrity` | `sip` | Urgency, distress, fake authority, and time-pressure attacks targeting verification bypass. |
| `social-engineering-cross-session-contamination.yaml` | `social-engineering-cross-session-contamination` | `adversarial` | `jailbreak`, `policy`, `pii_handling`, `role_integrity` | `sip` | Prior-session verification claims, fake agent notes, and memory-poisoning via context injection. |
| `policy-boundary-probe.yaml` | `policy-boundary-probe` | `adversarial` | `policy`, `jailbreak`, `pii_handling`, `role_integrity` | `sip` | Systematic six-probe policy edge mapping: competitors, legal liability, wellbeing, investment advice, dual-use. |
| `disclosure-indirect-extraction.yaml` | `disclosure-indirect-extraction` | `adversarial` | `disclosure`, `jailbreak`, `role_integrity`, `policy` | `sip` | Indirect system prompt extraction via reflection, contrast probing, error induction, persona naming, completion trap. |
| `inverse-jailbreak-harness-hardening.yaml` | `inverse-jailbreak-harness-hardening` | `adversarial` | `jailbreak`, `disclosure`, `role_integrity`, `policy` | `sip` | Hostile-bot inverse jailbreak against the harness caller. |
| `adversarial-branching-debug-authority.yaml` | `adversarial-branching-debug-authority` | `adversarial` | `jailbreak`, `disclosure`, `role_integrity`, `policy`, `reliability` | `sip` | Branching red-team attack chaining debug override, persistence, and fake-authority escalation. |
| `adversarial-branching-memory-exfil.yaml` | `adversarial-branching-memory-exfil` | `adversarial` | `jailbreak`, `disclosure`, `pii_handling`, `role_integrity`, `reliability` | `sip` | Memory-poisoning setup followed by log and cross-customer data exfiltration probes. |
| `adversarial-branching-asr-auth-bypass.yaml` | `adversarial-branching-asr-auth-bypass` | `compliance` | `pii_handling`, `policy`, `reliability`, `jailbreak`, `routing` | `sip` | Noisy-channel ambiguity test for auth bypass and unsafe confirmation handling. |
| `branching-smoke-sip.yaml` | `branching-smoke-sip` | `reliability` | `reliability` | `sip` | Minimal branching classifier smoke test over SIP. |
| `e2e-sip-mobile-smoke.yaml` | `e2e-sip-mobile-smoke` | `reliability` | `reliability` | `sip` | Real PSTN/SIP audio-path smoke test for TTS, STT, and judge round-trip. |
| `e2e-mock-bot-smoke.yaml` | `e2e-mock-bot-smoke` | `reliability` | `reliability` | `mock` | Local end-to-end smoke test without a SIP trunk. |
| `http-bot-smoke.yaml` | `e2e-http-bot-smoke` | `golden_path` | `routing`, `policy`, `reliability` | `mock` + HTTP profile | Minimal direct-HTTP smoke check for the standalone `http-test-bot`. |
| `monitoring-assistant-dashboard-handoff.yaml` | `monitoring-assistant-dashboard-handoff` | `golden_path` | `routing`, `policy`, `reliability` | `mock` + HTTP profile | Dashboard-summary smoke test for on-call handoff guidance. |
| `monitoring-assistant-anomaly-ranking.yaml` | `monitoring-assistant-anomaly-ranking` | `robustness` | `policy`, `routing`, `reliability`, `role_integrity` | `mock` + HTTP profile | Anomaly-risk ranking smoke test for monitoring assistant prioritization. |
| `monitoring-assistant-query-help.yaml` | `monitoring-assistant-query-help` | `golden_path` | `routing`, `policy`, `reliability` | `mock` + HTTP profile | PromQL authoring smoke test for monitoring assistant query help. |
| `monitoring-assistant-incident-triage.yaml` | `monitoring-assistant-incident-triage` | `golden_path` | `routing`, `policy`, `reliability` | `mock` + HTTP profile | Incident-response smoke test for first 10-minute triage guidance. |
| `monitoring-assistant-runbook-guidance.yaml` | `monitoring-assistant-runbook-guidance` | `golden_path` | `routing`, `policy`, `reliability` | `mock` + HTTP profile | Runbook and SOP guidance smoke test for monitoring assistant. |

## Which Example To Start From

- Start with `e2e-mock-bot-smoke.yaml` if you want a local pipeline check with
  no telephony dependency.
- Start with `http-bot-smoke.yaml` if you want a minimal graph scenario that
  runs through a direct HTTP destination instead of SIP.
- Start with the `monitoring-assistant-*.yaml` scenarios when you want a
  targeted dashboard/query/incident regression set for the Grafana monitoring
  assistant.
- Start with `golden-path-billing.yaml` if you need a small SIP-backed happy
  path to customize for your own bot.
- Start with `branching-smoke-sip.yaml` if you are validating the branching DSL
  or classifier path selection.
- Start with `compliance-pii-refusal.yaml` or `jailbreak-dan-prompt.yaml` if
  you need a targeted security/compliance baseline.
- Use the three `adversarial-branching-*` examples when you want richer
  red-team behavior that adapts based on the bot's observed response quality.
- Use `jailbreak-roleplay-persona-escape.yaml` or `jailbreak-hypothetical-framing.yaml`
  for character-framing and fiction-wrapper jailbreak regression.
- Use `social-engineering-urgency-pressure.yaml` and
  `social-engineering-cross-session-contamination.yaml` for social engineering
  and verification bypass regression.
- Use `policy-boundary-probe.yaml` for systematic policy edge discovery across
  competitor, legal, wellbeing, investment, and dual-use surfaces.
- Use `disclosure-indirect-extraction.yaml` for indirect system prompt leak
  detection via reflection, contrast, error induction, and completion traps.

## Packs

Pre-built packs in `../packs/examples/` group related scenarios for bulk execution:

| Pack file | Scenarios | What it covers |
| --- | --- | --- |
| `jailbreak-stress-pack.json` | 5 | Full jailbreak attack surface: DAN, persona escape, hypothetical framing, debug authority, inverse harness |
| `social-engineering-pack.json` | 4 | Social engineering: urgency/authority pressure, cross-session contamination, memory exfil, noisy-channel auth bypass |
| `full-red-team-battery.json` | 11 | Complete adversarial and compliance battery — all red-team scenarios, all gates must pass |
| `monitoring-assistant-http-pack.json` | 5 | Monitoring assistant targeted tasks: dashboard summary, anomaly ranking, query help, incident triage, runbook guidance |

## Notes

- The `Dimensions` column reflects the effective rubric resolved by the DSL,
  including defaults inherited from the scenario type.
- `sip` examples are designed for real telephony or SIP-backed staging checks.
- `mock` is the lowest-friction path for local development and CI.
- Direct HTTP examples use `bot.protocol: mock` today and rely on the selected
  destination/transport profile at run time. That keeps them compatible with the
  current scenario DSL while still exercising the HTTP runtime.
