# Scenario Builder (Graph Editor)

The Scenario Builder is a visual environment for authoring **Graph-based Scenarios**. These scenarios are structured as a state machine where each node represents a harness turn or a bot expectation, and edges define the conversation flow.

## Editor Layout

1. **The Canvas:** The main area where you place and connect nodes.
2. **The Toolbar:** Tools for adding new nodes, undoing/redoing changes, and zooming.
3. **Properties Panel:** Contextual editor for the selected node's content, assertions, and configuration.
4. **Validation Bar:** Real-time feedback on your scenario's structural integrity.

## Authoring Workflow

### 1. Adding Nodes
Add harness speaker nodes for what the synthetic caller says, and bot expectation nodes for what the bot under test is expected to reply.

### 2. Connecting Turns
Draw edges between nodes to define the sequence.
- **Linear Path:** Connect nodes in a straight line for a simple interaction.
- **Branching:** Use a **Branch Node** to define multiple possible paths based on the bot's response (e.g., if the bot says "billing" go to path A, if "support" go to path B).

### 3. Configuring Assertions
On each bot turn, define the criteria for success:
- **Intent Recognition:** Did the bot understand the caller?
- **Forbidden Phrases:** Ensure the bot doesn't say specific words or phrases.
- **Transfer Target:** Verify the call is transferred to the correct department.

### 4. Runtime Configuration
Set the "global" settings for the scenario:
- **TTS Voice:** Choose the voice for the harness (OpenAI, ElevenLabs).
- **Timeouts:** How long to wait for a bot response before failing.
- **Language:** The BCP-47 tag (e.g., `en-US`) for ASR and TTS.

## Validating and Saving
The builder will warn you if:
- A node has no path to the end.
- A branching node is missing a default path.
- Required fields (like turn text) are empty.

Once valid, save the scenario to make it available for execution in the **Runs** dashboard.
