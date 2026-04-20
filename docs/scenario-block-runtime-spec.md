# Scenario Block Runtime — Phase A Architecture Spec

Phase A of the scenario block improvements plan. Establishes the normalized
block-kind runtime model that all Phase B–D features build on.

---

## Problem Statement

The current graph runtime dispatches on `speaker == "bot"` vs `speaker == "harness"`.
Harness turns are further specialized by the presence of optional fields (`text`,
`audio_file`, `silence_s`, `dtmf`, `branching`, `builder_block`). Adding more
executable turn types (wait, time-of-day routing, assertions) as additional optional
fields would continue that pattern and make both the runner and the builder harder
to reason about and test.

The fix is a small, explicit discriminator field (`kind`) that drives dispatch
throughout the stack: DSL loading, runner execution, and builder node registry.

---

## Block Kinds

Six runtime block kinds cover the full scenario vocabulary:

| Kind | Phase | Description |
|---|---|---|
| `harness_prompt` | A | Harness plays content, optionally listens, optionally branches |
| `bot_listen` | A | Harness waits for bot to speak unprompted |
| `hangup` | A | Terminal end marker; no routing |
| `wait` | D | Clock-only pause; no audio, no listen window |
| `time_route` | D | Route by time-of-day; no audio, no listen window |
| `assert` | D | Assert on accumulated conversation state; no audio |

Phase A implements `harness_prompt`, `bot_listen`, and `hangup`. The Phase D kinds
slot in later without touching Phase A infrastructure.

---

## Normalized Block Schemas

### `harness_prompt`

Covers every case where the harness produces audio and optionally waits for a
bot response. Replaces the current `speaker == "harness"` turns.

```python
class PromptContent(BaseModel):
    """Exactly one of these must be set. Validated by HarnessPromptBlock."""
    text: str | None = None
    audio_file: str | None = None
    silence_s: float | None = None
    dtmf: str | None = None


class HarnessPromptBlock(BaseModel):
    kind: Literal["harness_prompt"] = "harness_prompt"
    id: str
    content: PromptContent               # exactly one field set; validated below
    listen: bool = True                  # from wait_for_response
    next: str | None = None              # simple linear routing
    branching: BranchConfig | None = None  # mutually exclusive with next
    max_visits: int = Field(default=1, ge=0)
    adversarial: bool = False
    technique: AdversarialTechnique | None = None
    expect: TurnExpectation | None = None
    config: TurnConfig = Field(default_factory=TurnConfig)

    @model_validator(mode="after")
    def validate_content_and_routing(self) -> "HarnessPromptBlock":
        content_fields = [
            self.content.text,
            self.content.audio_file,
            self.content.silence_s,
            self.content.dtmf,
        ]
        populated = [f for f in content_fields if f is not None]
        if len(populated) != 1:
            raise ValueError(
                f"harness_prompt block '{self.id}': exactly one content field required"
            )
        if self.branching is not None and self.next is not None:
            raise ValueError(
                f"harness_prompt block '{self.id}': cannot set both branching and next"
            )
        if self.adversarial and self.technique is None:
            raise ValueError(
                f"harness_prompt block '{self.id}': adversarial=true requires a technique"
            )
        return self
```

### `bot_listen`

Replaces `speaker == "bot"` turns. The harness opens a listen window without
emitting any audio first.

```python
class BotListenBlock(BaseModel):
    kind: Literal["bot_listen"] = "bot_listen"
    id: str
    next: str | None = None
    branching: BranchConfig | None = None
    max_visits: int = Field(default=1, ge=0)
    adversarial: bool = False
    technique: AdversarialTechnique | None = None
    expect: TurnExpectation | None = None
    config: TurnConfig = Field(default_factory=TurnConfig)

    @model_validator(mode="after")
    def validate_adversarial(self) -> "BotListenBlock":
        if self.adversarial and self.technique is None:
            raise ValueError(
                f"bot_listen block '{self.id}': adversarial=true requires a technique"
            )
        return self
```

### `hangup`

Terminal marker. No content, no routing. The runner closes the call after this
block executes.

```python
class HangupBlock(BaseModel):
    kind: Literal["hangup"] = "hangup"
    id: str
```

### Discriminated union

```python
from typing import Annotated, Union
from pydantic import Field

ScenarioBlock = Annotated[
    Union[HarnessPromptBlock, BotListenBlock, HangupBlock],
    Field(discriminator="kind"),
]
```

---

## Legacy Normalization Rules

The normalizer converts a legacy turn payload into a `ScenarioBlock`. This must
run on the raw mapping before legacy-only builder metadata is dropped and before
Pydantic attempts discriminated-union resolution. The runner only ever sees
`ScenarioBlock`.

```python
def load_block(raw_turn: dict[str, object]) -> ScenarioBlock:
    """
    Per-item loader for ScenarioDefinition.turns.

    Important: do not let Pydantic try ScenarioBlock.model_validate(raw_turn)
    before checking whether `kind` exists. In Pydantic v2 the discriminator is
    resolved eagerly, so a missing `kind` raises immediately and bypasses any
    legacy fallback.
    """
    if "kind" in raw_turn:
        return ScenarioBlockAdapter.validate_python(raw_turn)
    return normalize_legacy_turn_to_block(raw_turn)


def normalize_legacy_turn_to_block(raw_turn: dict[str, object]) -> ScenarioBlock:
    """Convert a legacy raw turn mapping into a normalized ScenarioBlock."""

    # bot_listen
    speaker = raw_turn.get("speaker")
    if speaker == "bot":
        turn = Turn(**raw_turn)
        return BotListenBlock(
            kind="bot_listen",
            id=turn.id,
            next=turn.next,
            branching=turn.branching,
            max_visits=turn.max_visits,
            adversarial=turn.adversarial,
            technique=turn.technique,
            expect=turn.expect,
            config=turn.config,
        )

    # hangup — builder signals this via builder_block="hangup" in raw YAML/UI state.
    # This branch must run before Turn(**raw_turn), because Turn.validate_content
    # rejects empty-content harness turns and Turn does not define builder_block.
    if raw_turn.get("builder_block") == "hangup":
        turn_id = str(raw_turn.get("id") or "").strip()
        if not turn_id:
            raise ValueError("Legacy hangup block requires a non-empty id")
        return HangupBlock(kind="hangup", id=turn_id)

    # remaining legacy shapes should validate as Turn first
    turn = Turn(**raw_turn)

    # harness_prompt — all remaining harness turns
    return HarnessPromptBlock(
        kind="harness_prompt",
        id=turn.id,
        content=PromptContent(
            text=turn.text,
            audio_file=turn.audio_file,
            silence_s=turn.silence_s,
            dtmf=turn.dtmf,
        ),
        listen=turn.wait_for_response,
        next=turn.next,
        branching=turn.branching,
        max_visits=turn.max_visits,
        adversarial=turn.adversarial,
        technique=turn.technique,
        expect=turn.expect,
        config=turn.config,
    )
```

The existing `ScenarioDefinition.turns` field becomes:

```python
# BEFORE
turns: list[Turn]

# AFTER (Phase A)
turns: list[ScenarioBlock]
```

`ScenarioDefinition.turns` therefore cannot be a plain `list[ScenarioBlock]`
field that relies on default discriminated-union parsing alone. Phase A needs a
custom per-item load path, for example a `field_validator("turns", mode="before")`
that maps every raw list item through `load_block(raw_turn)`.

The YAML loader upgrades each raw turn item through `load_block(raw_turn)`. This
means all existing scenario files continue to load without modification,
including legacy builder-authored hangup nodes that still rely on
`builder_block`.

---

## Runner Dispatch Contract

The loop executor dispatches on `block.kind` instead of `turn.speaker`:

```python
# BEFORE (scenario_loop_executor.py)
if turn_def.speaker == "bot":
    await execute_bot_speaker_turn(...)
    continue
await execute_harness_speaker_turn(...)

# AFTER
match block.kind:
    case "bot_listen":
        await execute_bot_listen_block(block, ...)
    case "harness_prompt":
        await execute_harness_prompt_block(block, ...)
    case "hangup":
        await execute_hangup_block(block, ...)
    case _:
        raise RuntimeError(f"Unknown block kind: {block.kind!r}")
```

Each block-kind executor receives only the fields relevant to its kind. Nothing
inside `execute_harness_prompt_block` needs to test `block.kind`.

Phase D adds three more `case` arms; the existing arms are unchanged.

### Mechanical rename contract

| Old entry point | New entry point | Block kind |
|---|---|---|
| `execute_bot_speaker_turn` | `execute_bot_listen_block` | `bot_listen` |
| `execute_harness_speaker_turn` | `execute_harness_prompt_block` | `harness_prompt` |
| *(none — hangup was implicit)* | `execute_hangup_block` | `hangup` |

The old entry points can be kept as thin wrappers during the transition and
removed once the builder and all tests reference the new names.

---

## Builder Mapping

The builder is aligned by updating `selectNodeTypeForTurn` and the node registry
descriptors to read and write the `kind` discriminator.

### Node type → block kind table

| Builder node type | Palette kind | Runtime block kind | Selector condition |
|---|---|---|---|
| `harnessNode` | `say_something` | `harness_prompt` | `kind == "harness_prompt"` (or legacy infer) |
| `harnessNode` (decision) | `decide_branch` | `harness_prompt` | same + `branching != null` |
| `harnessNode` (silence) | `listen_silence` | `harness_prompt` | same + `content.silence_s != null` |
| `botNode` | *(no palette entry)* | `bot_listen` | `kind == "bot_listen"` (or `speaker == "bot"`) |
| `hangupNode` | `hangup_end` | `hangup` | `kind == "hangup"` (or `builder_block == "hangup"`) |

### Updated `selectNodeTypeForTurn`

```typescript
// BEFORE
export function selectNodeTypeForTurn(turn: BuilderNodeTypeSelectorInput): BuilderNodeType {
  if (turn.builder_block === "hangup") return "hangupNode";
  return turn.speaker === "bot" ? "botNode" : "harnessNode";
}

// AFTER — kind takes priority; falls back to legacy inference
export function selectNodeTypeForTurn(turn: BuilderNodeTypeSelectorInput): BuilderNodeType {
  if (turn.kind === "hangup" || turn.builder_block === "hangup") return "hangupNode";
  if (turn.kind === "bot_listen" || turn.speaker === "bot") return "botNode";
  return "harnessNode";  // harness_prompt (all variants)
}
```

### Updated `NodeTypeDescriptor` contract

Each descriptor's `toYaml` writes the `kind` field into the output turn; each
`fromYaml` reads `kind` if present and ignores it when absent (backward
compat — the YAML loader handles that upgrade path). After Phase A, `kind`
becomes the canonical persisted marker; `builder_block` is retained only as a
legacy bridge for builder-authored hangup payloads during the transition:

```typescript
// hangupNode toYaml — adds kind to output
toYaml: (data) => ({
  ...data.turn,
  kind: "hangup",
  builder_block: "hangup",  // keep for legacy loaders during transition
}),
```

The `harnessNode` and `botNode` descriptors follow the same pattern:
- `toYaml` emits `kind: "harness_prompt"` / `kind: "bot_listen"`
- `fromYaml` accepts turns with or without `kind` (no breakage on existing saves)

---

## Migration Invariants

These must hold throughout Phase A and beyond:

1. **All existing scenario YAML files load without modification.** The raw-turn
   normalizer handles the upgrade transparently, including legacy builder-only
   markers such as `builder_block: hangup`.
2. **Current scenario behavior is identical after Phase A.** Block-kind dispatch
   produces the same execution trace as speaker-based dispatch for every existing
   supported turn shape.
3. **Node IDs and edge traversal semantics are unchanged.** Graph structure is
   unaffected; only the execution dispatch path and data model change.
4. **Builder round-trip is lossless for supported legacy shapes.** A scenario
   loaded from YAML, displayed in the builder, and re-serialized produces YAML
   that runs identically. After Phase A the serialized YAML includes `kind`
   fields, and the loader must no longer depend on `builder_block` surviving an
   API round-trip.
5. **Compatibility is explicit, not implied.** If a legacy field cannot be
   represented on a Phase A block kind, the loader must reject that shape with a
   clear validation error instead of silently dropping meaning.
6. **API migration is deliberate.** `ScenarioDefinition.turns` is an API field,
   so any flat-to-nested shape change must be paired with OpenAPI regeneration,
   web parser updates, and a compatibility story for existing builder consumers.

---

## Test Acceptance Criteria

### Normalization

- All legacy `speaker == "harness"` turns with each content type (`text`,
  `audio_file`, `silence_s`, `dtmf`) normalize to `HarnessPromptBlock`
- `speaker == "bot"` normalizes to `BotListenBlock`
- `builder_block == "hangup"` normalizes to `HangupBlock`
- A turn with no content fields raises `ValueError` at normalization time
- A turn with two content fields raises `ValueError` at normalization time
- A legacy YAML file without `kind` fields loads via the normalizer without error
- Missing `kind` does not trigger discriminated-union failure before the legacy
  normalizer runs
- A raw legacy hangup payload still normalizes correctly even though `Turn` does
  not define `builder_block`
- Bot-speaker legacy turns preserve `adversarial` and `technique` if those
  fields are present

### Runner dispatch

- `execute_scenario_loop` with a block list produces the same `conversation`
  output as the existing speaker-based loop for an equivalent turn list
- Each block-kind executor is called with the correct block type (no `isinstance`
  checks inside the executor)
- `hangup` blocks bypass pre-dispatch helper calls that assume `.config` /
  `.expect` / STT settings
- Existing `audio_file` and `dtmf` harness content paths are either implemented
  explicitly or rejected clearly; Phase A must not preserve the current silent
  no-op behavior under a renamed executor

### Builder

- `selectNodeTypeForTurn` returns the correct node type for each `kind` value
- `toYaml` on each descriptor emits the correct `kind` field
- A round-trip (parse → toYaml → parse) is lossless for every existing scenario
- Existing builder integration tests pass without modification
- OpenAPI regeneration updates the web scenario types cleanly and existing web
  typecheck continues to pass
- Flow translator/parser logic correctly handles both flat legacy turns and new
  Phase A kind-tagged turns; it must not silently assume `turn.text` /
  `turn.silence_s` remain top-level forever

---

## File Locations

| File | Change |
|---|---|
| `packages/scenarios/botcheck_scenarios/blocks.py` | New file — block kind models, discriminated union, `normalize_turn_to_block` |
| `packages/scenarios/botcheck_scenarios/dsl.py` | `ScenarioDefinition.turns` load path changed to custom per-item block loading; validators and helper methods updated for block kinds |
| `packages/scenarios/botcheck_scenarios/__init__.py` | Export new block types |
| `services/agent/src/scenario_loop_executor.py` | Dispatch on `block.kind` |
| `services/agent/src/scenario_bot_turn.py` | Rename `execute_bot_speaker_turn` → `execute_bot_listen_block`; accept `BotListenBlock` |
| `services/agent/src/scenario_harness_turn.py` | Rename `execute_harness_speaker_turn` → `execute_harness_prompt_block`; accept `HarnessPromptBlock`; migrate flat field access to `content.*`; close existing `audio_file` / `dtmf` execution gap |
| `services/agent/src/scenario_hangup.py` | New file — `execute_hangup_block` |
| `services/agent/src/graph.py` | Mechanical migration from `Turn` to `ScenarioBlock` / shared graph node protocol; traversal semantics unchanged |
| `services/agent/src/scenario_turn_cursor.py` | Mechanical type migration to block-based steps |
| `services/agent/src/scenario_turn_helpers.py` | `effective_turn_timeout`, `effective_stt_settings`, and related helpers must either operate on a shared protocol or move inside block-kind-specific dispatch paths |
| `web/src/lib/node-type-selector.ts` | Add `kind` check ahead of legacy `speaker` / `builder_block` checks |
| `web/src/lib/node-registry.ts` | `toYaml` emits `kind`; `fromYaml` accepts optional `kind` |
| `web/src/lib/builder-validation.ts` | Structural validation must understand `kind` and the normalized content shape during the transition |
| `web/src/lib/flow-translator/parser.ts` | Parse legacy turns and Phase A kind-tagged turns into a stable builder representation |
| `web/src/lib/flow-translator/serializer.ts` | Emit `kind` on write while preserving legacy-equivalent routing semantics |
| `web/src/lib/builder-types.ts` | Add optional `kind` field to `BuilderTurn` |
| `services/api/openapi*.json` / generated web API types | Regenerate API schema and downstream web types after `ScenarioDefinition` changes |

Graph layout semantics stay the same, but the graph and cursor modules still
need mechanical type migration because they are currently typed around `Turn`.

---

## Phase A Atomic Commit Plan

The critical rule for Phase A is: **do not land a commit where the loader, runner,
and builder/API disagree about the shape of `turns`.** The migration should move
from "legacy flat turns everywhere" to "normalized blocks everywhere" through
small but internally coherent steps.

### Commit 1. Add normalized block models and legacy loader

**Goal:** introduce the new block runtime types without changing execution yet.

**Changes:**
- add `blocks.py` with:
  - `PromptContent`
  - `HarnessPromptBlock`
  - `BotListenBlock`
  - `HangupBlock`
  - `ScenarioBlock` discriminated union
  - `load_block(raw_turn)`
  - `normalize_legacy_turn_to_block(raw_turn)`
- export new block types from `__init__.py`
- add unit tests for normalization only

**Do not change yet:**
- `ScenarioDefinition.turns`
- runner dispatch
- builder serialization
- OpenAPI

**Tests:**
- block-model validation
- legacy normalization, especially:
  - raw hangup payloads
  - bot turns with `adversarial` / `technique`
  - invalid legacy content shapes

### Commit 2. Switch DSL loading to block-based turns

**Goal:** make scenario loading return normalized blocks while keeping scenario
validation and helpers working.

**Changes:**
- update `ScenarioDefinition.turns` to load through per-item `load_block(raw_turn)`
- migrate `dsl.py` validators and helpers from `Turn` assumptions to block-aware logic:
  - at least one harness-like executable block
  - ID uniqueness
  - `next` / `branching` target validation
  - `adversarial_turns`
  - `turn_content_hash`
  - `turn_cache_key`
- explicitly document which helpers only apply to `harness_prompt` with `content.text`

**Tests:**
- existing scenario fixture files still load
- `turn_content_hash` / cache-key tests still pass for text prompts
- invalid graph edges still fail validation

### Commit 3. Migrate graph and cursor types

**Goal:** make traversal operate on blocks cleanly before touching the loop executor.

**Changes:**
- update `graph.py` from `Turn` to `ScenarioBlock` or a shared graph-node protocol
- update `scenario_turn_cursor.py` to return block-based steps
- keep traversal semantics identical:
  - `id`
  - `next`
  - `branching.cases[*].next`
  - `branching.default`
  - `max_visits`

**Tests:**
- existing graph traversal tests
- loop-cap behavior unchanged
- branch/default selection unchanged

### Commit 4. Move runner helper calls behind block-aware dispatch

**Goal:** remove the current pre-dispatch assumptions that every turn has
`.config`, `.expect`, and STT settings.

**Changes:**
- update `scenario_loop_executor.py` so timeout/STT helper calls happen inside
  the relevant `match block.kind` arms, not before dispatch
- update `scenario_turn_helpers.py` signatures if needed to operate on
  `HarnessPromptBlock | BotListenBlock` rather than generic `turn_def`
- add `scenario_hangup.py`

**Tests:**
- hangup blocks do not hit STT/timeout helpers
- existing speaker-path behavior still matches baseline traces

### Commit 5. Rename and migrate the runner executors

**Goal:** complete block-kind dispatch for runtime execution.

**Changes:**
- rename:
  - `execute_bot_speaker_turn` → `execute_bot_listen_block`
  - `execute_harness_speaker_turn` → `execute_harness_prompt_block`
- update `scenario_harness_turn.py` to use `content.*` instead of flat fields
- explicitly implement or reject `audio_file` and `dtmf` execution paths
- wire `execute_hangup_block` into the loop executor

**Tests:**
- conversation trace parity against representative legacy scenarios
- explicit regression tests for:
  - text prompt
  - silence prompt
  - bot-listen opening turn
  - hangup execution
  - `audio_file`
  - `dtmf`

### Commit 6. Add builder dual-read / canonical-write support

**Goal:** let the builder read legacy turns and write Phase A turns with `kind`.

**Changes:**
- update `builder-types.ts` for optional `kind`
- update `node-type-selector.ts` to prefer `kind`, then legacy fallback
- update `node-registry.ts` so `toYaml` emits `kind`
- update parser/serializer and builder validation for:
  - flat legacy turns
  - kind-tagged Phase A turns
- keep `builder_block` only as a temporary hangup bridge

**Tests:**
- existing builder tests
- round-trip tests for:
  - legacy YAML → builder → Phase A YAML
  - Phase A YAML → builder → Phase A YAML
- hangup node remains stable through round-trip

### Commit 7. Regenerate API schema and web types

**Goal:** make the API contract explicit and keep the web build green.

**Changes:**
- regenerate OpenAPI
- regenerate web API types
- update web parser/type surfaces that still assume flat turn fields

**Tests:**
- API schema generation
- `npm --prefix web run typecheck`
- targeted builder/parser tests

### Commit 8. Remove temporary compatibility seams

**Goal:** clean up the Phase A migration once all consumers are on `kind`.

**Changes:**
- remove old runner wrapper entry points if no longer needed
- reduce legacy-only builder fallbacks where safe
- keep legacy turn YAML loading, but stop depending on `builder_block` after
  builder/API round-trip

**Tests:**
- full scenario load suite
- full agent tests for graph scenarios
- builder regression suite

---

## Recommended Execution Gates

Do not start Commit 4 until Commits 1-3 are merged.

Do not start Commit 6 until Commit 5 is merged.

Do not remove compatibility seams in Commit 8 until:
- scenario fixtures load in both legacy and `kind` form
- builder round-trip passes on both legacy and Phase A YAML
- OpenAPI/web type regeneration is green
