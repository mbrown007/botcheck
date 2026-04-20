# Scenario Execution Flow (Cold Cache & Branching)

This diagram illustrates the lifecycle of a test run where the TTS cache is cold (requiring JIT synthesis) and the scenario contains adaptive branching logic.

```mermaid
sequenceDiagram
    autonumber
    participant U as User / Scheduler
    participant API as BotCheck API
    participant LK as LiveKit Server
    participant H as Harness Agent
    participant S3 as S3 TTS Cache
    participant TTS as TTS (OpenAI)
    participant STT as STT (Deepgram)
    participant CL as Classifier (Haiku)
    participant B as Bot Under Test
    participant J as Judge Service

    Note over U, API: 1. Initialization
    U->>API: POST /runs/ {scenario_id}
    API->>LK: Create Room & Dispatch Harness
    API->>API: Set state = PENDING
    API-->>U: 202 Accepted (run_id)

    Note over H, B: 2. Connection
    H->>API: GET /scenarios/{id}
    H->>LK: Join Room
    H->>H: Initialize Graph Traversal
    LK->>H: Bot Participant Joined
    H->>API: POST /runs/{id}/turns (run_started)

    Note over H, TTS: 3. Harness Turn (Cold Cache)
    H->>S3: GET {tenant}/tts-cache/{content_hash}.wav
    S3-->>H: 404 Not Found (MISS)
    H->>TTS: POST /v1/audio/speech (Synthesize)
    TTS-->>H: Audio Stream (WAV)
    H->>LK: Publish Audio Track
    LK->>B: [[ "Hello, how can I help?" ]]

    Note over B, CL: 4. Bot Response & Branching
    B->>LK: [[ "I need help with billing" ]]
    LK->>H: Audio Stream (PCM)
    H->>STT: Stream Audio
    STT-->>H: Transcript: "billing"
    H->>CL: POST (Transcript + Branch Conditions)
    Note right of CL: "bot offers billing" vs "bot offers tech support"
    CL-->>H: Chosen: "billing_branch"
    H->>H: Advance Graph to 't2_billing'
    H->>API: POST /runs/{id}/turns (turn_executed + branch_decision)

    Note over H, J: 5. Completion & Judging
    H->>API: POST /runs/{id}/complete {conversation}
    API->>API: Set state = JUDGING
    API->>J: Enqueue 'judge_run' (ARQ)
    J->>API: GET /scenarios/{id} (Rubric)
    J->>J: Evaluate Deterministic Rules
    J->>J: Call Claude 3.5 Sonnet (LLM Scoring)
    J->>API: PATCH /runs/{id} {scores, findings, gate_result}
    API->>API: Set state = COMPLETE | FAILED
```

### **Key Interaction Details:**

1.  **Orchestration (Steps 1-5):** The API acts as the control plane, setting up the environment and handing off execution to the Harness Agent via LiveKit Dispatches.
2.  **The Cache Miss (Steps 11-13):** Because the cache is cold, the Harness performs JIT (Just-In-Time) synthesis. This adds ~200-500ms of latency compared to a **Warm Cache** hit.
3.  **Adaptive Branching (Steps 18-21):** The Harness doesn't follow a fixed list. It uses a fast LLM (Claude Haiku) to classify the bot's response against the YAML `branching` conditions, allowing the test to "chase" the bot down different logic paths.
4.  **Fail-Closed Judging (Steps 23-28):** Completion is separate from scoring. The Harness provides the evidence, and the Judge Service performs the heavy lifting of multi-sample scoring and deterministic verification before the API issues the final `PASSED` or `BLOCKED` status.
