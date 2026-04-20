# Transport Profile Examples

This directory contains curated transport-profile payload examples for the
Destinations API. These files match the `BotDestinationUpsert` API shape.

Use them when you want to:

- test a bot directly over HTTP before exposing it on SIP
- model authenticated internal chat endpoints
- document request and response field mapping for operators

## Example Index

| File | Best for | What it demonstrates |
| --- | --- | --- |
| `direct-http-basic.json` | Local or staging smoke checks | Minimal HTTP profile with default request and response field names. |
| `direct-http-authenticated.json` | Internal bot APIs behind a bearer token | Header auth plus custom request and response field names. |
| `direct-http-session-history.json` | Stateful bot APIs | Session ID and history field mapping with higher retry tolerance. |
| `monitoring-assistant-local-sse.json` | Local Grafana assistant development | Targets `POST /api/chat` with SSE responses and BotCheck-managed `session_id`. |

## Create A Transport Profile

```bash
curl -X POST http://localhost:8000/destinations/ \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/json' \
  --data @scenarios/transport-profiles/examples/direct-http-basic.json
```

## Notes

- HTTP profiles snapshot their headers and mapping config onto runs at creation
  time. Changing the destination later does not rewrite an in-flight run.
- Keep secrets out of git. Replace the placeholder tokens in these files before
  using them in a real environment.
- HTTP profiles can now include `direct_http_config.request_body_defaults` for
  shared request-body fields. Scenario-level `http_request_context` can override
  or extend those defaults per run.
- `monitoring-assistant-local-sse.json` is intended for local or staging runs
  against `/api/chat` when the assistant is configured with
  `eval_bypass_auth: true` or equivalent auth headers/cookies are supplied.
