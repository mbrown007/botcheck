# Generated Schemas

These JSON Schema artifacts are generated from canonical Pydantic models.
Regenerate them with:

```bash
uv run python scripts/generate_schemas.py
```

| File | Canonical model | Purpose | Notes |
| --- | --- | --- | --- |
| `scenario-definition.json` | `botcheck_scenarios.dsl.ScenarioDefinition` | Root BotCheck graph-scenario DSL model | Includes nested persona, runtime config, turns, and scoring contracts. |
| `scenario-config.json` | `botcheck_scenarios.turns.ScenarioConfig` | Reusable runtime configuration embedded in scenario definitions | Covers timing, TTS, and STT fields used by graph scenarios. |
| `speech-capabilities.json` | `botcheck_scenarios.speech.SpeechCapabilities` | Shared `/features` speech capability contract | Captures the provider capability surface exposed to Builder and AI Scenarios. |
| `ai-scenario-upsert-request.json` | `botcheck_api.scenarios.schemas.AIScenarioUpsertRequest` | Current AI-scenario authoring API contract | The `config` field remains a freeform object in this slice because AI runtime config does not yet have a dedicated shared Pydantic model. |

Generated files in this directory should not be edited by hand.
