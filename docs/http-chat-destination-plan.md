# HTTP Chat Destination Plan

## Summary

BotCheck already has the runtime needed to call chat-style HTTP agents. The missing piece is product shape, not a new transport engine.

Today HTTP transport profiles support:

- JSON request bodies
- JSON responses
- plain-text responses
- SSE responses
- configurable request and response field mapping

That is already enough to support agents like `monitoring-assistant-http` without hard-coding anything specific to that service.

This plan defines how to make chat-style HTTP agents first-class destinations in BotCheck by:

- adding an explicit stored HTTP subtype
- improving the transport-profile UI for HTTP chat patterns
- exposing request defaults for richer request bodies
- standardizing auth as a service-to-service concern

The target outcome is that operators can add any compatible HTTP chat agent as a destination by configuring a reusable HTTP transport profile, then selecting it in runs, schedules, packs, playground, and eval flows.

## Current State

### What BotCheck already supports

The current direct HTTP transport already exists and is generic:

- destination CRUD stores `protocol: "http"` plus `direct_http_config`
- run dispatch snapshots HTTP transport config into the run
- the shared HTTP client supports:
  - JSON request payload construction
  - dotted field-path extraction for JSON responses
  - SSE response parsing from `text/event-stream`
  - retries and timeouts

This means a chat agent does not require:

- a new protocol
- a new runtime transport
- any monitoring-assistant-specific execution code

### What feels incomplete today

- the HTTP form is still framed as low-level `Direct HTTP Mapping`
- the UI does not distinguish generic JSON APIs from chat-style JSON + SSE agents
- `request_body_defaults` exists in the backend contract but is not surfaced well in the main settings UI
- auth is not modeled cleanly enough for server-to-server chat endpoints
- the operator has to infer which fields matter for SSE chat and which do not

## Monitoring Assistant Contract

The monitoring assistant is a good reference target because it is a normal HTTP chat API, not a BotCheck-native runtime.

### Request shape

`POST /api/chat`

JSON body:

- `message`
- optional `session_id`
- optional `dashboard_context`
- optional `selected_context`

### Response shape

The endpoint streams `text/event-stream` SSE events.

Each `data:` line is a JSON `StreamChunk` containing fields such as:

- `type`
- `message`
- optional `session_id`

### Important implications

- `request_text_field = "message"` is correct
- `request_session_id_field = "session_id"` is correct
- `request_history_field` should be blank for this agent
- `response_text_field` is not the primary extraction path for this endpoint because BotCheck already switches to SSE parsing based on content type

This confirms that the correct product move is to support a reusable HTTP chat pattern, not to special-case this agent.

## Core Decision

Add an explicit stored HTTP subtype.

Recommended field:

- `direct_http_config.http_mode`

Initial allowed values:

- `generic_json`
- `json_sse_chat`

This should live inside `direct_http_config`, not as a new top-level destination protocol.

### Why store it explicitly

Storing the subtype is better than making it a UI-only preset because it gives BotCheck a stable contract for:

- validation
- rendering
- future migrations
- future API clients
- clearer run snapshots

It also lets the system distinguish between two HTTP profiles that are both `protocol: "http"` but operationally different.

### What it should not do

`http_mode` should not create separate runtime engines.

The runtime remains one generic direct HTTP transport. The subtype should mainly control:

- form defaults
- field visibility
- validation rules
- labels and descriptions

## Target Product Model

### Top-level protocol stays unchanged

The transport profile protocol list remains:

- `sip`
- `http`
- `webrtc`
- `mock`

### HTTP transport gets a second-level mode

When `protocol === "http"`, the operator also chooses:

- `Generic JSON API`
- `JSON Request + SSE Reply`

Stored as:

```json
{
  "direct_http_config": {
    "http_mode": "json_sse_chat"
  }
}
```

### Meaning of each mode

#### `generic_json`

Use when the endpoint returns:

- JSON with a scalar field path
- plain text

Typical examples:

- `{ "response": "hello" }`
- `{ "data": { "answer": "hello" } }`
- plain text response body

#### `json_sse_chat`

Use when the endpoint:

- accepts a JSON request body
- streams `text/event-stream`
- emits chat chunks or token chunks

Typical examples:

- internal AI chat APIs
- assistant endpoints like monitoring assistant
- any server-to-server SSE chat surface

## Auth Model

### Recommendation

Use service-to-service header auth, not browser session cookies.

Preferred patterns:

1. `Authorization: Bearer <token>`
2. `X-BotCheck-Token: <token>`

### Why this is the right model

- works for manual runs, schedules, packs, and playground
- not tied to a browser session
- not tied to a specific user
- easier to rotate and audit
- fits server-to-server dispatch

### What to avoid

- Grafana session cookie auth as the primary BotCheck integration method
- auth bypass except for local development

### Monitoring Assistant expectation

Monitoring assistant currently authenticates `/api/chat` in normal mode. If BotCheck is going to call it directly, the clean product path is:

- BotCheck sends a configured service token in headers
- monitoring assistant validates that token

This is cleaner than trying to mint or replay Grafana session cookies from BotCheck.

## UI Design

## Transport Profile Form

When protocol is `HTTP`, show:

- `HTTP Destination Type`
- `Endpoint URL`
- `HTTP Request Mapping`
- `HTTP Auth Headers`
- optional `Default Request Context`

### `HTTP Destination Type`

Values:

- `Generic JSON API`
- `JSON Request + SSE Reply`

### For `Generic JSON API`

Show:

- request text field
- history field
- session ID field
- response text field
- timeout
- max retries

### For `JSON Request + SSE Reply`

Show:

- request text field
- session ID field
- optional JSON defaults
- timeout
- max retries

Hide or de-emphasize:

- history field
- response text field

Reason:

- most chat SSE endpoints do not accept a BotCheck-style `history` array
- response extraction is driven by `text/event-stream`, not a JSON response field

### Labels

Replace `Direct HTTP Mapping` with more operator-friendly copy:

- `HTTP Request Mapping`
- or `HTTP Chat Mapping`

Avoid making the UI sound like an internal transport-debug panel.

## Data Model Changes

### Backend schema

Extend `DirectHTTPTransportConfig` with:

- `http_mode: Literal["generic_json", "json_sse_chat"] = "generic_json"`

Keep existing fields:

- `method`
- `request_content_type`
- `request_text_field`
- `request_history_field`
- `request_session_id_field`
- `request_body_defaults`
- `response_text_field`
- `timeout_s`
- `max_retries`

### Validation changes

For `http_mode == "json_sse_chat"`:

- require `request_text_field`
- allow `request_session_id_field`
- allow `request_body_defaults`
- allow `request_history_field` to be blank
- allow `response_text_field` to be omitted or ignored

For `http_mode == "generic_json"`:

- current validation mostly remains

### Backward compatibility

Existing HTTP destinations with no `http_mode` should default to:

- `generic_json`

This avoids breaking existing profiles and snapshots.

## Request Body Defaults

This is the main capability the current UI is missing for richer chat agents.

`request_body_defaults` should be surfaced as an advanced JSON editor for HTTP transport profiles.

Use cases:

- `dashboard_context`
- `selected_context`
- feature flags
- environment routing hints
- agent-specific static context

For monitoring assistant, this enables useful payloads like:

```json
{
  "dashboard_context": {
    "uid": "ops-overview",
    "time_range": {
      "from": "now-6h",
      "to": "now"
    }
  }
}
```

This remains generic and should not reference monitoring assistant by name in the product UI.

## Suggested Monitoring Assistant Profile

For the current agent, the intended transport profile should look like:

- Name: `monitoring-assistant-http`
- Protocol: `HTTP`
- HTTP Destination Type: `JSON Request + SSE Reply`
- Endpoint: `http://<host>:<port>/api/chat`
- Request Text Field: `message`
- Session ID Field: `session_id`
- History Field: blank
- Timeout: `30`
- Max Retries: `1`
- Headers:
  - `Authorization: Bearer <service-token>` or equivalent
- Optional request defaults:
  - `dashboard_context`
  - `selected_context`

## Implementation Slices

### Slice 1: Backend schema and validation

Add `http_mode` to `DirectHTTPTransportConfig`.

Files:

- `services/api/botcheck_api/packs/destinations.py`
- `services/api/botcheck_api/packs/service_destinations.py`
- `web/src/lib/api/types.ts`
- generated OpenAPI artifacts if required by repo workflow

Acceptance:

- existing HTTP profiles still work
- new profiles can persist `http_mode`
- `json_sse_chat` profiles validate correctly with blank history field

### Slice 2: HTTP transport profile UI

Add `HTTP Destination Type` to the HTTP form and update labels.

Files:

- `web/src/app/(dashboard)/settings/_components/TransportProfileSettingsCard.tsx`

Acceptance:

- operators can choose between generic JSON and JSON + SSE chat
- the form hides irrelevant fields for SSE chat mode
- saved profile rows show the HTTP subtype clearly

### Slice 3: Advanced request defaults

Expose `request_body_defaults` in the HTTP form behind an advanced section.

Files:

- `web/src/app/(dashboard)/settings/_components/TransportProfileSettingsCard.tsx`

Acceptance:

- valid JSON can be entered and saved
- invalid JSON is rejected with a clear error
- defaults round-trip through the API

### Slice 4: Header-based auth support in product flow

Make sure the HTTP form supports editable request headers in a clean way and document the auth expectation.

Files:

- transport-profile UI
- docs and runbooks as needed

Acceptance:

- operators can configure bearer-token or custom-header auth without code changes
- no agent-specific fields are introduced

### Slice 5: Monitoring assistant verification

Create one real transport profile for the monitoring assistant and verify:

- profile saves
- BotCheck can dispatch to it
- SSE response is consumed correctly
- no `history` field is required
- auth is satisfied via configured headers

This slice is verification, not product hard-coding.

## Risks

### 1. Over-modeling HTTP too early

Adding too many HTTP subtypes too quickly would create a taxonomy problem.

Mitigation:

- start with only two modes
- keep the runtime generic

### 2. UI complexity

Adding advanced HTTP features can make the settings page heavy again.

Mitigation:

- keep `request_body_defaults` in an advanced section
- simplify the chat-mode form rather than exposing every field equally

### 3. Auth drift between local and production

The local monitoring-assistant setup may use bypass auth or a different port than the intended long-term deployment.

Mitigation:

- document header-based auth as the intended model
- treat bypass auth as local-only

## Recommendation

Proceed with an explicit stored HTTP subtype.

That gives BotCheck a durable contract for chat-style HTTP destinations without introducing a new runtime or baking in monitoring-assistant-specific behavior.

The recommended steady state is:

- `protocol = http`
- `direct_http_config.http_mode = json_sse_chat`
- request defaults exposed in UI
- service-to-service header auth

That is the cleanest path to supporting `monitoring-assistant-http` now while also making BotCheck more useful for other HTTP chat agents later.
