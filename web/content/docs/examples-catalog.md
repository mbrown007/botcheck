# Example Catalog

BotCheck now ships example assets for the three main authoring paths:

- graph scenarios
- AI scenarios
- packs and transport profiles

Use these files as copyable starting points. They are small on purpose. Each
example demonstrates one pattern clearly instead of trying to cover every
option in one file.

## Where To Look

### Graph scenarios

Repo path: `scenarios/examples/`

Start here when you need a runnable graph scenario with the DSL already wired.
The catalog in that directory includes happy-path, compliance, adversarial, SIP
smoke, and mock smoke examples.

### AI scenarios

Repo path: `scenarios/ai-scenarios/examples/`

These examples match the AI Scenarios API payload shape. They are useful when
you want to seed intent-first scenarios through the API or copy a proven brief
into the UI.

- `routing-handoff-escalation.json`
- `adversarial-off-task-jailbreak.json`
- `pii-verification-refusal.json`

### Packs

Repo path: `scenarios/packs/examples/`

These examples show two common pack shapes:

- a small HTTP smoke pack
- a mixed AI-plus-graph regression pack

Use them when you are building scheduled suites or CI-triggered regression
runs.

### Transport profiles

Repo path: `scenarios/transport-profiles/examples/`

These examples are for direct bot testing before SIP exposure. They show how
to map BotCheck turns to your bot's HTTP request and response contract.

- `direct-http-basic.json`
- `direct-http-authenticated.json`
- `direct-http-session-history.json`

## Suggested Order

1. Start with `scenarios/examples/e2e-mock-bot-smoke.yaml` for local graph
   validation.
2. Add a direct HTTP profile from `scenarios/transport-profiles/examples/`.
3. Create one AI scenario from `scenarios/ai-scenarios/examples/`.
4. Group the checks into a pack from `scenarios/packs/examples/`.
5. Once the bot is stable, add a SIP transport profile and run the same pack
   over telephony.

## Notes

- Example transport profiles contain placeholder tokens. Replace them before
  use.
- Example AI scenarios assume the backing graph scenario and persona already
  exist in your tenant.
- Packs stay transport-agnostic. Choose the transport profile when you run or
  schedule them.
