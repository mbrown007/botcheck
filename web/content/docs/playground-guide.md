# Scenario Playground

The Playground is a browser-based sandbox for running scenarios without SIP telephony. It lets you iterate on conversation logic, adversarial framing, and scoring thresholds in seconds rather than waiting for a full production run.

## When to use the Playground

| Use case | Best tool |
| :--- | :--- |
| Tune a system prompt and see how a bot responds to specific harness turns | Playground (mock mode) |
| Verify a live HTTP bot handles a new adversarial turn sequence | Playground (direct HTTP) |
| Run a full regression suite on a SIP voicebot | Schedule / Pack run |
| Confirm gate thresholds before production deploy | Full SIP run |

Playground runs produce a real run report scored by the same judge. They appear in the Runs list and count against your run quota.

---

## Modes

### Mock Mode

The bot under test is an in-process LLM agent driven by a system prompt you supply. No external service is called for bot responses.

**When to use it:** Writing a new scenario, exploring branching logic, or testing adversarial framing without needing a deployed bot.

- Supply a free-text system prompt in the editor.
- Optionally load a saved AI Persona as a starting point via the persona picker.
- Optionally configure tool stubs (see [Tool Stubs](#tool-stubs) below).

### Direct HTTP Mode

The bot under test is a real HTTP bot endpoint you have already configured in Settings → Transport Profiles.

**When to use it:** Validating that a specific staging or production bot handles a scenario correctly without placing a SIP call.

- Select an active HTTP transport profile. Auth headers and request mapping are inherited from the profile.
- System prompt and tool stubs are not available in this mode.

---

## Running a Playground Session

1. Select a scenario from the **Scenario** dropdown.
   - Graph scenarios are filtered to mock and HTTP transports only.
   - AI scenarios use their bound runtime graph.
2. Choose **Mock Agent** or **Direct HTTP**.
3. Fill in the mode-specific controls.
4. Click **Run Playground**.

The run is dispatched through the normal pipeline. The two right-hand panes update in real time via a persistent SSE event stream.

---

## Live Activity Feed

The left pane shows every event as the scenario executes:

| Event | Appearance |
| :--- | :--- |
| Harness turn | Right-aligned bubble, brand colour |
| Bot reply | Left-aligned bubble, neutral colour |
| Branch decision | Full-width card with selected/skipped chips |
| Expectation result | Chip row with pass / fail / warn tone |
| Run complete | Green summary bar at the top of the feed |

The **Pause Scroll** button stops auto-scrolling so you can read earlier events while the run continues.

---

## Turn Progress Pane

The right pane renders the scenario's turn graph. Each node shows:

- Turn ID and speaker
- Current status: pending, active, passed, failed, or skipped
- Text preview (first line of the harness utterance or branch condition)
- Branch case chips — the selected branch is highlighted, unchosen branches are dimmed

Once the run completes, an **Open full run detail** link appears at the bottom.

---

## Tool Stubs

Tool stubs let you define what values the mock bot "sees" when it calls a tool. This is useful for scenarios that test how a bot uses lookup results.

### Step 1 — Extract tools

Click **Extract Tools**. BotCheck scans the system prompt for explicitly described callable tools and creates an editor card for each one.

### Step 2 — Edit or generate stub values

Each card shows the tool name, description, and a JSON editor pre-filled with `{}`.

- **Edit manually:** Type any valid JSON object into the editor.
- **Generate Values:** Click the button to let BotCheck suggest plausible stub values grounded in the selected scenario.

If any editor contains invalid JSON, the **Run Playground** button is disabled and the offending tool names are listed in red.

### Stub persistence

Stubs are saved to `sessionStorage` keyed by scenario ID. They survive page refresh but are cleared when you close the tab.

---

## AI Scenario Debug Panel

For AI scenario playground runs, a collapsible **Harness Reasoning** panel appears below the session feed. It shows the harness's internal decision events in chronological order:

| Entry | What it shows |
| :--- | :--- |
| Classifier input | The bot transcript excerpt seen by the intent classifier |
| Classifier output | The selected case (e.g., `continue`, `escalate`) and optional confidence |
| Caller reasoning | A plain-language summary of why the harness chose its next utterance |

The panel is collapsed by default. Its open/closed state persists in `localStorage`.

> This panel is absent for graph scenario runs. Graph scenarios use deterministic branching and produce no harness reasoning events.

---

## Quotas and limits

- Playground runs share the same run quota as regular runs.
- SIP telephony is not available in the Playground. Attempting to select a SIP-only scenario returns a 422 error.
- The mock agent system prompt has a soft limit of 16,000 characters. Longer prompts are accepted but may degrade mock bot coherence.
- Tool stubs are per-session only. They are not saved to the scenario definition.
