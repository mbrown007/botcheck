# Grai Evals — User Guide

Grai Evals is BotCheck's large-scale HTTP eval system. It lets you import a
[promptfoo](https://www.promptfoo.dev/) YAML test suite, run every prompt × case
pair against a live HTTP bot destination, and view pass/fail results with
per-assertion breakdown.

---

## Concepts

| Term | Meaning |
|---|---|
| **Eval suite** | A collection of prompts and test cases, imported from promptfoo YAML |
| **Prompt** | A template string with optional `{{variable}}` placeholders |
| **Case** | A set of variable values + one or more assertions to evaluate |
| **Eval run** | A single execution of a suite against a specific transport profile |
| **Transport profile** | An HTTP destination (endpoint URL + field mapping) the bot is reached on |
| **Assertion** | A check applied to the bot's response (see types below) |

---

## Supported assertion types

| Type | What it checks |
|---|---|
| `contains` | Response contains the expected string (case-sensitive) |
| `icontains` | Response contains the expected string (case-insensitive) |
| `word-count` | Response has at least N words (threshold field) |
| `llm-rubric` | Claude judges the response against a rubric string |
| `regex` | Response matches a regular expression |
| `javascript` | Custom JS expression evaluates to truthy |

---

## Importing an eval suite

1. Navigate to **Grai Evals** in the sidebar.
2. Click **Import Suite**.
3. Paste or upload a promptfoo YAML file.
4. BotCheck converts it to a native eval suite and shows an import summary.

### Supported promptfoo fields

```yaml
prompts:
  - "Answer the user question clearly: {{question}}"

tests:
  - vars:
      question: "What is the refund policy?"
    assert:
      - type: contains
        value: "refund"
  - vars:
      question: "How do I contact billing support?"
    assert:
      - type: icontains
        value: "support"
  - vars:
      question: "I need help with a payment issue."
    assert:
      - type: word-count
        threshold: 3
```

Fields not listed above are imported and stored but may not be evaluated.

---

## Creating a transport profile (HTTP destination)

A transport profile tells the eval worker how to call your bot.

1. Go to **Settings → Transport Profiles**.
2. Click **Add Transport Profile**.
3. Fill in:

| Field | Value |
|---|---|
| **Name** | Human-readable label, e.g. `mock-http-bot` |
| **Protocol** | `HTTP` |
| **Endpoint URL** | Full URL of the bot's chat endpoint |
| **Request Text Field** | JSON key for the user message (default: `message`) |
| **History Field** | JSON key for conversation history (default: `history`) |
| **Session ID Field** | JSON key for the session identifier (default: `session_id`) |
| **Response Text Field** | JSON key to read the bot's reply from (default: `response`) |
| **Timeout (s)** | Request timeout in seconds (default: 30, max: 120) |
| **Max Retries** | Retry attempts on failure (default: 1, max: 3) |

4. Click **Create Transport Profile**.

### Docker networking — important

If the eval worker and your bot both run in Docker Compose, use the **Docker
service name** as the host, not `localhost`:

```
# Wrong — localhost inside the container refers to the container itself
http://localhost:8081/chat

# Correct — other containers reach the bot by service name on its internal port
http://http-test-bot:8080/chat
```

`localhost:<port>` in the destination URL only works when calling from your host
machine (browser/curl). The eval worker runs inside Docker and must use the
service name.

---

## Running an eval

1. Open the **Grai Evals** page.
2. Select an eval suite from the dropdown.
3. Select a transport profile.
4. Click **Run Eval**.

The run starts immediately and polls for progress. Each prompt × case pair is
dispatched concurrently (up to the configured concurrency limit).

---

## Reading results

### Progress view

While running, the progress panel shows:
- Total pairs dispatched / completed / failed
- Live status: `pending → running → complete / failed`

### Report view

Once complete, the **Report** tab shows:
- Overall pass / fail counts
- Breakdown by assertion type
- Failing prompt variants
- Tag-based failure clusters
- Exemplar failures with the actual bot response and failure reason

### Results table

The **Results** tab lists every pair with:
- Prompt text (after variable substitution)
- Case description
- Assertion type
- Pass/fail
- Failure reason (e.g. *"response did not contain 'refund'"*)

---

## The mock HTTP test bot

BotCheck ships a lightweight scripted bot (`services/http-test-bot`) for local
testing without needing a real external bot.

### Starting it

```bash
docker compose up -d http-test-bot
```

It starts on `127.0.0.1:8081` (host) / port `8080` (Docker internal).

### Verifying it is up

```bash
curl http://localhost:8081/health
# → {"status":"ok","mode":"scripted"}
```

### Sending a test message

```bash
curl -s http://localhost:8081/chat \
  -X POST -H "Content-Type: application/json" \
  -d '{"message": "What is the refund policy?"}'
# → {"response":"Our refund policy allows refunds within 30 days of purchase."}
```

### Bot modes

| Mode | Behaviour | Set via |
|---|---|---|
| `scripted` (default) | Keyword-matched responses from a JSON map | `HTTP_BOT_MODE=scripted` |
| `echo` | Echoes the message back | `HTTP_BOT_MODE=echo` |
| `ai` | Calls OpenAI GPT-4o-mini | `HTTP_BOT_MODE=ai` + `OPENAI_API_KEY` |

### Customising scripted responses

The response map is set via the `HTTP_BOT_RESPONSE_MAP_JSON` environment
variable in `docker-compose.yml`. Keyword matching is case-insensitive and
checks whether the keyword appears anywhere in the message.

Default map (matches the bundled eval suite assertions):

```json
{
  "refund": "Our refund policy allows refunds within 30 days of purchase.",
  "billing support": "Please contact our billing support team at support@example.com.",
  "payment": "Our support team can help with payment issues. Please contact us."
}
```

To change without rebuilding the image, edit the value in `docker-compose.yml`
and run:

```bash
docker compose up -d http-test-bot
```

### Using the mock bot as an eval destination

In **Settings → Transport Profiles**, create a profile with:

| Field | Value |
|---|---|
| Protocol | `HTTP` |
| Endpoint URL | `http://http-test-bot:8080/chat` |
| Request Text Field | `message` |
| History Field | `history` |
| Session ID Field | `session_id` |
| Response Text Field | `response` |
| Timeout | `30` |
| Max Retries | `1` |

Use `http://http-test-bot:8080/chat` (not `localhost:8081`) because the eval
worker runs inside Docker.

---

## Troubleshooting

### Eval run stuck in `pending`

The eval worker is not running. Start it:

```bash
docker compose up -d eval-worker
docker compose logs eval-worker --tail=20
```

It should print `Starting worker for 1 functions: run_grai_eval` once ready.

### Eval run fails immediately with `ConnectError: All connection attempts failed`

The eval worker cannot reach the endpoint URL. Common causes:

- **Used `localhost` in the URL** — change to the Docker service name
  (`http://http-test-bot:8080/chat`).
- **Bot container not running** — `docker compose ps` and start it if needed.
- **Wrong internal port** — Docker Compose maps ports. Use the *container*
  port in the destination URL, not the *host* port.

### All assertions failing with `response did not contain '...'`

The bot's responses do not match the assertion values. Either:

1. Update the bot's `HTTP_BOT_RESPONSE_MAP_JSON` to return responses that
   contain the expected strings.
2. Update the eval suite assertions to match what the bot actually returns.

### `function min(boolean) does not exist` in eval-worker logs

SQLite-only `min(boolean)` used against PostgreSQL — fixed in the current
codebase. Rebuild the containers:

```bash
docker compose build api eval-worker && docker compose up -d api eval-worker
```

### Eval worker logs show `ModuleNotFoundError`

The worker image is stale and missing a workspace package. Rebuild:

```bash
docker compose build eval-worker && docker compose up -d eval-worker
```
