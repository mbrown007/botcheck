# Phase 8 Builder Sign-off Checklist (2026-03-01)

## Scope

Visual Flow Builder delivery across Sprint 1-5:
- Translator + round-trip parity (`yamlToFlow` / `flowToYaml`)
- Builder store + dual canvas/YAML sync model
- Builder navigation/actions (new/import/export/copy/open-in-builder)
- Branch edge interactions + labels/default handling
- Harness Play preview integration
- Workspace polish (collapsible/resizable right blade, metadata editor, keyboard shortcuts)

## Automated Evidence

Local verification run on 2026-03-01:

```bash
npm --prefix web run test:unit
npm --prefix web run lint
npm --prefix web run typecheck
```

Results:
- `test:unit`: 62 passed
- `lint`: pass
- `typecheck`: pass

CI coverage now includes:
- Web lint + typecheck + unit tests (`web` job)
- Browser smoke on Playwright Chromium (`web-e2e-smoke` job, `@smoke` grep)

## Exit Criteria Trace

| Exit Criterion | Evidence | Status |
|---|---|---|
| EC-1: 5-turn branching scenario can be built and saved with no console errors | Playwright builder save/reload flow + builder unit tests | Covered (CI smoke + local) |
| EC-2: Round-trip preserves schema/ordering and validates cleanly | `flow-translator` unit suite + validate/save paths | Covered |
| EC-3: Visual/YAML switching stability | Store/translator smoke tests + parse-error guard tests | Covered |
| EC-4: Node positions stable across reloads | `flow-layout-storage` + Playwright persisted panel/layout flows | Covered |
| EC-5: Scenarios → Builder → Scenarios with unsaved-change guard | Builder route/open-in-builder + `beforeunload` behavior in page implementation | Covered |
| EC-6: Exported YAML validates | Export path + validation tests | Covered |
| EC-7: Play button behavior by cache state/error handling | Harness preview tests + feature gating + 429 handling | Covered |

## Remaining Phase 8 Notes

- One non-blocking architecture note remains in plan backlog:
  - node type selection coupling (`updateNodeTurn` depends directly on `selectNodeTypeForTurn`)
- Optional pre-close staging drill:
  - run the Playwright smoke in staging-like env and attach the artifact link to this file.
