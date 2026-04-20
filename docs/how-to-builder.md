# User Guide: Visual Flow Builder

The **Visual Flow Builder** provides a drag-and-drop interface for creating and editing BotCheck scenarios. It allows you to visualize complex branching logic and manage scenario metadata without writing raw YAML.

---

## 1. Accessing the Builder

There are two main entry points:
1.  **Sidebar:** Click the **Scenario Builder** link in the navigation blade. This opens an empty canvas for a new scenario.
2.  **Edit Action:** From the **Scenarios** library list, click the **Open in Builder** button on any existing scenario.

---

## 2. Core Building Blocks (The "Semantic 6")

The builder uses six specialized nodes to represent scenario logic:

1.  **Start Block (Scenario Context):** 
    *   **Color:** Grey/Circle
    *   **Usage:** The immovable entry point. Click this to edit the scenario ID, name, persona mood, and global configuration (like the default TTS voice).
2.  **Say Block (Harness Speech):**
    *   **Color:** Blue
    *   **Usage:** What the harness agent will say. Includes a **Play** button to preview the TTS synthesis.
3.  **Listen Block (Bot Collection):**
    *   **Color:** Green
    *   **Usage:** Represents the harness waiting for the bot to speak. Use this to add **Expect Assertions** (e.g., "Must say 'Account Balance'").
4.  **Decide Block (Intelligent Branching):**
    *   **Color:** Amber/Diamond
    *   **Usage:** Routes the conversation based on the bot's response. Add multiple output handles, each with a natural language condition (e.g., "Bot offers help with billing").
5.  **Pause Block (Injected Silence):**
    *   **Color:** Slate
    *   **Usage:** Injects a specific duration of silence into the call. Great for testing barge-in or silence robustness.
6.  **Hangup Block (Terminal State):**
    *   **Color:** Red
    *   **Usage:** Signals the end of the test. Once reached, the harness will hang up the SIP call.

---

## 3. Building Branching Logic

To create a non-linear conversation:
1.  Add a **Decide Block**.
2.  Drag an edge from a **Listen Block** to the Decide Block.
3.  Add output edges from the Decide Block to other blocks.
4.  **Label the Edges:** Click on an edge to add a natural language condition that Claude will use to "route" the call in real-time.
5.  **The Default Path:** One edge from a Decide Block must always lead to a **Default** path if no conditions match.

---

## 4. Bidirectional YAML Sync

The builder maintains a "Dual-Mode" relationship with the underlying YAML:
*   **Visual View:** Best for structuring logic and branching.
*   **YAML View:** Best for power users to perform bulk edits or add advanced configuration fields not yet supported by visual nodes.
*   **Sync:** Changes in the visual canvas are debounced and synced to the YAML pane. Edits in the YAML pane are applied to the canvas when you click **Apply** or blur the editor.

---

## 5. Persistence and Layout

*   **Auto-Layout:** Use the **Zoom Fit** and **Arrange** buttons to automatically organize your nodes using the `dagre` engine.
*   **Local Storage:** The builder automatically remembers your manual node positions in your browser's local storage, ensuring your layout remains stable even if you don't save the scenario immediately.
*   **Save:** Click the **Save** button (or `Ctrl+S`) to persist the YAML and current version hash to the server.
