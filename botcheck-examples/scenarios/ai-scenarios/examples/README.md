# AI Scenario Examples

This directory contains curated AI scenario payload examples for the BotCheck
AI Scenarios feature. These files match the `AIScenarioUpsertRequest` API
shape.

Use them when you want to:

- seed a new AI scenario through the API
- copy a proven intent pattern into the UI
- build a pack that mixes graph scenarios and AI scenarios

## Before You Use Them

Each example references:

- a backing `scenario_id` from `scenarios/examples/`
- a `persona_id` that must exist in your tenant

Replace the `persona_id` values with a real persona before posting these files
to `/scenarios/ai-scenarios`.

## Example Index

| File | Uses | Backing graph scenario | What it demonstrates |
| --- | --- | --- | --- |
| `routing-handoff-escalation.json` | Routing smoke and escalation quality | `golden-path-billing` | Intent-first routing validation with a calm but insistent caller. |
| `adversarial-off-task-jailbreak.json` | Red-team and off-task resistance | `jailbreak-dan-prompt` | Caller tries to drag the bot away from policy and extract hidden instructions. |
| `pii-verification-refusal.json` | PII and verification policy | `compliance-pii-refusal` | Caller pressures the bot to disclose protected data without verification. |

## Post Through The API

```bash
curl -X POST http://localhost:8000/scenarios/ai-scenarios \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  --data @scenarios/ai-scenarios/examples/routing-handoff-escalation.json
```

## Notes

- Leave speech/runtime overrides blank in the UI when you want platform
  defaults. These examples set them explicitly so provider behavior is easy to
  study.
- The `scenario_facts` objects are intentionally small. Add only the facts the
  harness needs to behave credibly.
