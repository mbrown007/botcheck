# How to Add, Run, and Schedule Scenarios

This guide provides a step-by-step walkthrough for the primary user workflows in the BotCheck dashboard.

---

## 1. Adding a Scenario

A **Scenario** is the core testing unit in BotCheck. It defines the conversation between the synthetic caller (harness) and the AI agent under test.

### Steps:
1.  **Navigate to Scenarios:** Click the **Scenarios** link in the left-hand navigation bar.
2.  **Upload Scenario:** Click the **Upload Scenario** button at the top right.
3.  **Use a Template:** 
    *   Select an **Adversarial Pack Template** (e.g., "Golden Path" or "DAN Jailbreak") to populate the editor with a validated starting point.
    *   Alternatively, paste your own YAML directly into the editor.
4.  **Configure Persona:** Use the **Harness Persona Controls** to adjust the mood (e.g., Happy, Angry) and response style (e.g., Curt, Verbose). Click **Apply Persona to YAML** to sync these settings.
5.  **Validate:** Click the **Validate** button. The dashboard will check for schema errors or logic issues (like infinite loops).
6.  **Upload:** Once valid, click **Upload** to save the scenario to your tenant library.

---

## 2. Running a Scenario

You can trigger a test run manually to observe real-time behavior.

### Steps:
1.  **Select Scenario:** Find your scenario in the library list and click **View**.
2.  **Trigger Run:** Click the **Run** button.
3.  **Choose Endpoint (Optional):** You can override the default SIP/WebRTC endpoint for this specific run if needed.
4.  **Observe Live:** You will be redirected to the **Run Detail** page. Here you can watch:
    *   **Timeline:** The state transitions (Pending -> Running -> Judging).
    *   **Transcript:** Real-time speech-to-text conversion of both the harness and the bot.
    *   **Audio Preview:** If the turn is already cached, you can listen to the harness audio before it plays.

---

## 3. Reviewing Results

Once a run reaches the **Complete** state, the automated judge will provide a verdict.

### Key Metrics:
*   **Gate Result:** `PASSED` (green) means all critical security and quality thresholds were met. `BLOCKED` (red) means a failure was detected.
*   **Dimension Scores:** View individual scores for **Jailbreak Resistance**, **PII Handling**, **Routing Accuracy**, and **Reliability**.
*   **Findings:** Scroll down to see specific evidence cited by the judge, including transcript snippets and severity levels.
*   **Speech Timing:** Review deterministic metrics like **P95 Response Gap** and **Interruption Recovery** to assess the "human-like" quality of the agent.

---

## 4. Scheduling Automated Tests

Schedules allow you to run scenarios automatically at specific intervals (e.g., every hour) to detect regressions in production agents.

### Steps:
1.  **Navigate to Schedules:** Click **Schedules** in the left-hand navigation bar.
2.  **Create Schedule:** Click **New Schedule**.
3.  **Configure Frequency:**
    *   Select a scenario from your library.
    *   Choose a frequency (Hourly, Daily, Weekly) or enter a custom **Cron Expression**.
4.  **Set Timezone:** Select the target timezone for the schedule. The UI will show you a preview of the next 5 execution times.
5.  **Save:** Click **Create**. The background scheduler will now handle dispatching these runs and acquiring the necessary SIP slots.

### Monitoring Schedules:
*   Use the **Schedules Dashboard** to toggle schedules on/off or check the **Last Status** (e.g., Dispatched, Throttled, Failed).
*   Check the **Delivery & Ops** dashboard in Grafana to see the aggregate health of your automated testing pipeline.
