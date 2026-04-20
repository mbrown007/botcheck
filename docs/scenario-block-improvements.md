# Scenario Block Improvements

Improvements to the outbound (graph) scenario DSL, runner, and builder UI.
Each item maps to one or more atomic commits. Status: `[ ]` todo · `[~]` in progress · `[x]` done.

Important implementation note: the current graph runtime is still fundamentally a
`speaker="harness"` / `speaker="bot"` turn engine with a few special fields, not a
generalized block runtime. This plan now assumes we will fix that first and build on an
explicit block runtime rather than continuing to extend the legacy turn shape with more
one-off fields.

---

## 0. Runtime Shape Decision

**Status:** `[x]`

**Problem:** Several planned features (`time_of_day_routing`, `wait_s`,
`assert_on_conversation`, and possibly `listen_for_s`) assume the scenario runtime can
execute generalized non-audio blocks. Today it cannot: harness turns are still validated
as audio / prompt-producing turns and the runner dispatches almost entirely on
`speaker == "bot"` vs harness speak/listen behavior.

**Decision:** choose **Option B: first-class block kind**.

**Why:**
- We already want multiple non-audio executable blocks (`time_of_day_routing`, `wait_s`,
  `assert_on_conversation`) plus richer branching.
- The current turn model is already carrying too many semantics through loosely-related
  optional fields.
- Builder work is easier to reason about if node kinds map to explicit runtime block kinds
  instead of inferred combinations of fields.

**Chosen direction:**
- Introduce an explicit discriminator in the DSL/runtime model
- Make runtime execution dispatch on block kind, not only on `speaker`
- Keep the graph/edge model, IDs, and traversal semantics
- Add a compatibility layer so existing scenario YAML can still load while the builder and
  runtime migrate

**Foundation principles:**
- **Stable graph identity:** preserve node IDs and edge traversal semantics during the
  migration
- **Block-local validation:** each block kind owns its own schema and validation rules
- **Runtime normalization:** load legacy turn YAML into a normalized runtime block model
  before execution
- **Builder parity:** node palette, registry, parser, serializer, and editor contracts
  should map directly to block kinds
- **Backwards compatibility first:** existing scenarios must continue to parse and run
  during the transition

**Initial block families to support:**
- `harness_prompt`
- `bot_expect`
- `decision`
- `hangup`
- `wait`
- `time_route`
- `assert`
- `dtmf_prompt` may stay a builder alias over `harness_prompt` initially if we do not want
  a separate runtime kind yet

**Commits (planned):**
1. `docs: scenario blocks adopt first-class block runtime`
2. `refactor: scenarios (dsl): add normalized block-kind runtime model with legacy loader`
3. `refactor: agent (runner): dispatch scenario execution by block kind`
4. `refactor: builder (ui): align node registry and translator with explicit block kinds`

**Tests / outputs:**
- Design note describing the chosen runtime shape and migration rules
- Loader tests proving legacy turn YAML normalizes into block kinds
- Runner tests proving block-kind dispatch preserves current scenario behavior
- Updated implementation slices below to build on the block runtime

---

## 1. Fixed-Duration Listen (`listen_for_s`)

**Status:** `[ ]`

**Problem:** Silence detection (`stt_endpointing_ms` + `merge_window_s`) is unreliable when
the bot plays hold music, reads back long confirmations, or when STT lag is inconsistent.
Need a way to collect audio for exactly N seconds then advance — either grabbing whatever
transcript accumulated or deliberately ignoring it (pure barge-in interrupt).

**Architecture note:** under the block-runtime plan this belongs on the block kind that
waits for/responds to bot audio, not as an ad hoc field on every possible turn shape.
It is still an early candidate because it fits the existing listen path well.

**Touches:**
- `packages/scenarios/botcheck_scenarios/` — add `listen_for_s` to the appropriate normalized block config
- `services/agent/src/audio.py` — in `BotListener.listen()`, when `listen_for_s` is set bypass silence detection entirely (`asyncio.sleep(listen_for_s)` then drain accumulated transcript)
- `services/agent/src/scenario_bot_listener.py` — thread `listen_for_s` through to `BotListener.listen()`
- `web/src/` — expose this as an advanced timing override on the relevant prompt/listen block editor

**Commits (planned):**
1. `feat: scenarios (dsl): add listen_for_s to bot-listen block config`
2. `feat: agent (audio): fixed-duration listen bypasses silence detection`
3. `feat: builder (ui): expose listen_for_s on bot-listen capable blocks`

**Tests:**
- Unit: `listen_for_s` set → `asyncio.sleep` called, endpointing not used
- Unit: `listen_for_s` not set → existing silence detection path unchanged

---

## 2. Time-of-Day Routing Block

**Status:** `[ ]`

**Problem:** IVR systems and voicebots often present different menus or route differently
outside business hours. Need to test the right path without maintaining separate scenario
files or hardcoding assumptions about when the test runs.

**Architecture note:** this is now explicitly planned as a first-class non-audio block
kind on top of the shared block runtime foundation.

**DSL shape:**
```yaml
- id: time_check
  speaker: harness
  time_of_day_routing:
    timezone: "Europe/London"
    windows:
      - label: business_hours
        start: "08:00"
        end: "16:00"
        next: t_business
      - label: evening
        start: "16:00"
        end: "22:00"
        next: t_evening
    default: t_overnight
  wait_for_response: false
```

**Touches:**
- `packages/scenarios/botcheck_scenarios/` — add `TimeOfDayWindow`, `TimeOfDayRouting`, and the normalized `time_route` block kind
- `services/agent/src/` — execute `time_route` through block-kind dispatch, not as a special case inside harness playback
- `web/src/` — routing-capable node/editor support wired to the explicit block kind; this affects palette, registry, parser/serializer, and edge authoring

**Commits (planned):**
1. `feat: scenarios (dsl): add time_route block kind`
2. `feat: agent (runner): execute time-of-day routing blocks`
3. `feat: builder (ui): add time-of-day routing node and edge editor support`

**Tests:**
- Unit: window matching logic (boundary conditions, midnight wrap, timezone conversion)
- Unit: turn with no matching window uses default
- Integration: time-of-day turn in scenario advances to correct next turn

---

## 3. DTMF Palette Block (Builder)

**Status:** `[ ]`

**Problem:** The builder already exposes `dtmf` in the harness turn editor, but it is not
discoverable as a first-class action in the palette. IVR flows are possible today, but the
authoring experience is weak and visually indistinct from a generic harness node.

**No new runtime behavior needed** if DTMF remains a builder-first variant of an existing
prompt block. Keep this as a UX improvement unless we later decide DTMF needs its own
runtime kind.

**Touches:**
- `web/src/lib/builder-blocks.ts` — new `press_dtmf` block kind
- `web/src/lib/node-registry.ts` — register dtmf node descriptor
- `web/src/components/builder/` — DTMF node component (phone keypad / digit string input, optional post-DTMF listen toggle, optional `listen_for_s` override)
- `web/src/app/(dashboard)/builder/_components/TurnBlocksPalette.tsx` — add to palette
- `web/src/lib/flow-translator/` — serialise/deserialise dtmf turn to/from YAML

**Commits (planned):**
1. `feat: builder (ui): add DTMF-first node/palette affordance`

**Tests:**
- Builder: DTMF block serialises to correct turn DSL shape
- Builder: digit string validation (only 0-9, *, #, A-D)

---

## 4. Keyword / Regex Branch (Fast Branch, No LLM)

**Status:** `[ ]`

**Problem:** The current `decide_branch` block uses an LLM classifier (~1-2s latency,
token cost) to pick a path. For simple "did the bot say X?" routing — IVR menu detection,
transfer announcements, booking references — regex is instant and deterministic.

**Architecture note:** under the block-runtime plan, branch matching rules can evolve, but
the graph still needs a stable branch selector independent of the human-facing label or
match expression. Preserve that explicitly.

**DSL shape:**
```yaml
- id: menu_heard
  text: "I'd like to book an appointment."
  wait_for_response: true
  branching:
    mode: keyword           # "classifier" (current default) | "keyword" | "regex"
    cases:
      - match: "press 1"    # substring match (mode: keyword)
        next: press_1_path
      - match: "press 2"
        next: press_2_path
      - regex: "reference\\s+number\\s+([A-Z]\\d{6})"   # (mode: regex)
        next: reference_path
    default: fallback_path
```

**Touches:**
- `packages/scenarios/botcheck_scenarios/` — extend the `decision` block config with `mode`, `selector`, `match`, and `regex` semantics while preserving a stable branch key
- `services/agent/src/scenario_turn_helpers.py` — add non-LLM branch evaluation path for keyword/regex modes
- `web/src/` — "Match mode" toggle on decision blocks, with separate human-facing edge labels if needed

**Commits (planned):**
1. `docs: decision block selector and match schema`
2. `feat: scenarios (dsl): extend decision blocks with keyword and regex modes`
3. `feat: agent (runner): keyword and regex branch evaluation`
4. `feat: builder (ui): match mode toggle on decision block`

**Tests:**
- Unit: keyword match (case-insensitive, substring)
- Unit: regex match (valid pattern, capture group ignored for routing)
- Unit: regex invalid pattern → validation error at scenario load time
- Unit: `mode="classifier"` unchanged behaviour
- Unit: `mode="keyword"` with no `match` → validation error

---

## 5. Wire Up `retry_on_silence`

**Status:** `[ ]`

**Problem:** `TurnConfig.retry_on_silence` already exists in the DSL and is documented,
but is not enforced in the main loop. Scenarios that rely on it silently misbehave.

**No new builder concept needed** if retry remains part of the normalized prompt/listen
block config.

**Touches:**
- `services/agent/src/scenario_harness_turn.py` — after the listen path returns `"(timeout)"`, replay the same harness turn up to N additional times before advancing
- keep retry accounting local to the harness-turn execution path; do not overload graph cursor visit counts with retry attempts

**Commits (planned):**
1. `fix: agent (runner): enforce retry_on_silence when bot is silent`

**Tests:**
- Unit: bot silent on first attempt, `retry_on_silence=2` → harness replays twice
- Unit: bot responds on second attempt → loop exits, transcript captured
- Unit: bot silent throughout → after N retries, advances normally with `"(timeout)"`

---

## 6. Explicit Wait Block (`wait_s`)

**Status:** `[ ]`

**Problem:** The current way to pause is `silence_s: 2.0` which plays actual PCM silence
into the call. This is correct when you need to feed audio (e.g. holding open the mic
during hold music) but semantically wrong when you just want the scenario clock to tick
without touching the audio stream — e.g. waiting for a transfer to connect.

**Architecture note:** this is an explicit non-audio block kind under the chosen runtime
model, not a semantic overload of `silence_s`.

**DSL shape:**
```yaml
- id: wait_for_transfer
  wait_s: 8.0
  wait_for_response: false   # No listen window — just clock ticks
```

**Touches:**
- `packages/scenarios/botcheck_scenarios/` — add `wait` block kind with `wait_s`
- `services/agent/src/` — execute wait blocks through block-kind dispatch
- `web/src/` — wait/pause node support across palette, registry, parser/serializer, and editor UI

**Commits (planned):**
1. `feat: scenarios (dsl): add wait block kind`
2. `feat: agent (runner): execute wait blocks as clock-only pause`
3. `feat: builder (ui): wait/pause node support`

**Tests:**
- Unit: `wait_s` turn sleeps for correct duration, emits no audio
- Unit: `wait_s` + `wait_for_response: true` → validation error (nonsensical combination)

---

## 7. Loop Block (Builder UX for `max_visits`)

**Status:** `[ ]`

**Problem:** The DSL already supports loop-back via `max_visits` on a turn and a `next`
edge pointing back to an earlier turn. But the builder has no way to express or visualise
this clearly. Common in real scenarios: retry prompts, hold
music loops, repeated menu offers.

**Reality check:** `max_visits` is already editable in the builder; the missing piece is
visual feedback and clearer back-edge authoring, not raw loop capability. Under the
block-runtime plan, loop affordances should still remain graph-level UX, not a separate
runtime block kind.

**Touches:**
- `web/src/lib/flow-translator/` — detect a back-edge (target node has lower `orderIndex` than source); annotate edge as `kind: "loop_back"`; serialise `max_visits` on the target node
- `web/src/components/builder/` — render loop-back edges with a distinctive style (curved, arrow pointing back); show `max_visits` badge on the target node; add "max loop iterations" input to node editor
- `web/src/app/(dashboard)/builder/_components/BuilderCanvas.tsx` — allow back-edges (currently may be blocked by validation)

**Commits (planned):**
1. `feat: builder (ui): loop-back edge support and max_visits badge`

**Tests:**
- Builder: back-edge serialises to correct `next` + `max_visits` DSL shape
- Builder: loop-back edge renders without cycle errors in React Flow

---

## 8. Static Assertion Block

**Status:** `[ ]`

**Problem:** `expect` assertions are attached to individual turns. If a turn is skipped via
branching its assertions are never evaluated. No way to assert on conversation state at a
branch convergence point.

**Architecture note:** this is another explicit non-audio block kind on top of the chosen
block runtime foundation.

**DSL shape:**
```yaml
- id: confirm_routed_correctly
  assert_on_conversation:
    transcript_contains: "transferring"
    transcript_not_contains: "unable to help"
    min_turns: 2
    max_turns: 6
  wait_for_response: false
```

**Touches:**
- `packages/scenarios/botcheck_scenarios/` — add `ConversationAssert` model and normalized `assert` block kind
- `services/agent/src/` — execute assertion blocks against accumulated conversation through block-kind dispatch
- `web/src/` — assert/checkpoint node support across palette, registry, parser/serializer, and editor UI

**Commits (planned):**
1. `feat: scenarios (dsl): add assert block kind`
2. `feat: agent (runner): evaluate static assertion blocks`
3. `feat: builder (ui): assert/checkpoint node support`

**Tests:**
- Unit: `transcript_contains` passes when substring present
- Unit: `transcript_not_contains` fails turn when substring found
- Unit: `min_turns` / `max_turns` boundary checks
- Integration: assert turn after a branch convergence evaluates correctly

---

## Delivery Order

| # | Feature | DSL | Runner | Builder | Priority |
|---|---|---|---|---|---|
| 0 | Block runtime foundation | Yes | Yes | Yes | **Highest** |
| 5 | Wire up retry_on_silence | — | Yes | — | **High** |
| 1 | Fixed-duration listen | Yes | Yes | Yes | **High** |
| 4 | Keyword / regex branch | Yes | Yes | Yes | **High** |
| 3 | DTMF palette affordance | — | — | Yes | **Medium** |
| 7 | Loop block (builder UX) | — | — | Yes | **Medium** |
| 6 | Explicit wait block | Yes | Yes | Yes | **Medium** |
| 2 | Time-of-day routing | Yes | Yes | Yes | **Medium** |
| 8 | Static assertion block | Yes | Yes | Yes | **Medium** |

---

## Recommended Implementation Phases

### Phase A: Foundation
1. Adopt the normalized block-kind runtime model with legacy scenario loading
2. Move runner dispatch onto block kind while preserving current scenario behavior
3. Align builder node registry and translator contracts with explicit block kinds

### Phase B: Low-risk wins on the new foundation
1. Wire up `retry_on_silence`
2. Add `listen_for_s`
3. Add keyword/regex branching

### Phase C: Builder UX improvements
1. Add DTMF-first palette/node affordance
2. Improve loop/back-edge authoring and visual feedback

### Phase D: New non-audio executable blocks
1. Add `wait`
2. Add `time_route`
3. Add `assert`
