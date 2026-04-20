# Managing Runs

A **Run** is a single execution of a scenario. It represents a "live" call from the BotCheck Harness to your voicebot.

## Viewing Individual Runs

When you open a run in the dashboard, you can see its current state and detailed results:

### 1. The Transcript (Live)
As the call progresses, you'll see a real-time transcript of the interaction between the harness (the caller) and your bot.
- **Harness Turns:** What the harness is saying.
- **Bot Turns:** What the bot is saying (via ASR).
- **Latency Data:** View the STT and TTS latency for each turn.

### 2. The Audio (Live)
Listen to the call as it happens. After the call is complete, you can replay the audio recording from the "Audio Artifacts" panel.

### 3. The Judge's Report
Once the call ends, the Judge analyzes the conversation and provides:
- **Scoring Dimensions:** View scores for each dimension (e.g., routing, policy, jailbreak).
- **Findings:** Specific issues found during the call (e.g., "Bot failed to recognize intent on turn 3").
- **Reasoning:** A detailed explanation from the Judge for each score.

## Run Status and Gate Result

- **Pending:** The run is waiting to be dispatched.
- **Running:** The call is currently in progress.
- **Judging:** The conversation has ended, and the Judge is scoring the transcript.
- **Complete/Failed:** The final state of the run.
- **Gate Result:** "Passed" or "Blocked" based on your scenario's thresholds.

## Filtering and Searching
The Runs dashboard allows you to filter by:
- **Scenario ID**
- **Tenant ID**
- **Date Range**
- **Gate Status** (e.g., show only failing runs)
