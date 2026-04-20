# Provider Admin Flow Redesign

## Summary

The current provider admin experience is structurally misaligned with the actual admin workflow.

Today the page is centered on platform credential management. The intended operational workflow is:

1. Create a provider entry.
2. Assign that provider to exactly one tenant.
3. Review usage and set quotas for that assigned tenant.

This document defines the target product model, the backend contract changes required to support it cleanly, and the frontend redesign needed to make the flow obvious and low-friction.

## Current Problems

### UI problems

- The current two-pane provider page is catalogue-first, not workflow-first.
- The primary detail pane is a credential editor, even though credential management is only one step in the overall flow.
- `tenant_assignment_count` is the wrong abstraction if the intended rule is one provider per tenant.
- The page pushes assignment and quota management into tenant admin, which forces the operator to mentally jump between two surfaces for one job.
- The existing state tiles explain status, but they do not guide the admin to the next action.
- ENV-backed resolution is too visible in the main UI, which creates noise and makes the page feel more complex than the intended steady state.

### Contract problems

- Provider assignment is currently tenant-centric in the API.
- The backend does not currently enforce a one-provider-to-one-tenant invariant.
- The inventory response does not expose the assigned tenant directly.
- Cost metadata exists, but there is no clear admin workflow around it.

## Target Product Model

### Provider

A provider is a model-level runtime entry with:

- `capability`
- `vendor`
- `model`
- `label`
- platform credential
- optional cost metadata

`provider_id` remains `vendor:model`.

### Assignment rule

Each provider may be assigned to at most one tenant.

This is not just a UI simplification. It is the operational rule for cost tracking and should become a backend invariant.

### Quota rule

Quotas are configured only for assigned providers.

Quota metrics remain capability-specific:

- `llm`: `input_tokens`, `output_tokens`, `requests`
- `judge`: `input_tokens`, `output_tokens`, `requests`
- `tts`: `characters`, `requests`
- `stt`: `audio_seconds`, `requests`

### Credential model

The intended steady state is BotCheck-managed stored credentials, not `.env`-backed configuration.

ENV-backed runtime resolution may remain as a backend fallback during migration, but it should not dominate the primary admin experience.

## UX Goals

- Make the provider workflow obvious from one page.
- Remove the need to jump between provider admin and tenant admin for the same task.
- Make assignment state visually obvious.
- Make the next action obvious for every provider.
- Make quota management feel attached to the assigned provider, not like a separate admin system.
- Preserve enough diagnostic detail for support without surfacing legacy runtime details as primary UI state.

## Core Decisions

### 1. Split the library into Assigned and Available

The provider library should be presented as two sections:

- `Assigned Providers`
- `Available Providers`

This replaces the current “select row in catalogue, inspect detail pane” model.

### 2. Make assignment provider-centric

Assignment and unassignment should be initiated from the provider page.

New provider-centric endpoints should be added under the provider admin router:

- `POST /admin/providers/{provider_id}/assign`
- `DELETE /admin/providers/{provider_id}/assign`

### 3. Enforce one-provider-per-tenant at the service layer

When assigning provider `P` to tenant `T`, any prior assignment of `P` to another tenant must be removed or replaced atomically.

The UI must not be the only layer assuming 1:1 assignment.

### 4. Replace assignment count with assigned tenant info

Provider inventory should expose a nullable assigned tenant object instead of `tenant_assignment_count`.

Target shape:

```json
{
  "assigned_tenant": {
    "tenant_id": "tenant_123",
    "tenant_name": "Acme Corp",
    "enabled": true
  }
}
```

When unassigned:

```json
{
  "assigned_tenant": null
}
```

Transitional note:

The assignment row currently also carries `is_default` and `effective_credential_source`.

Those fields are not needed for the provider-page redesign itself, but they should not be removed blindly in the first backend slice because existing tenant-admin flows still reference them.

Recommended handling:

- enforce the one-provider-to-one-tenant invariant first
- move the provider admin UI to the new flow
- then remove or redesign legacy assignment-only fields once the remaining tenant-admin usage has been simplified

### 5. Use one provider modal with two modes

The primary interaction should be one modal or drawer with two modes:

- `Assign`
- `Manage`

This keeps the mental model tight and avoids page fragmentation.

### 6. Keep ENV fallback, but de-emphasize it

ENV fallback should remain a backend/runtime compatibility path until migration is complete.

But in the admin UI:

- do not use `ENV` as a primary status badge on cards
- do not make “env vs stored” the top-level story
- keep any fallback indication in low-prominence diagnostic copy only

### 7. Treat external pricing sync as advisory, not authoritative

Vendor pricing APIs are not a reliable cross-provider foundation for this feature.

Imported price data should be treated as:

- optional
- reviewable
- overrideable

Manual cost metadata remains the source of truth.

## Target UI

## Page Layout

Replace the current two-pane layout with two stacked sections:

1. Header
2. `Assigned Providers`
3. `Available Providers`

Header actions:

- `Add Provider`
- optional future `Refresh Suggested Prices`

### Assigned provider card

Each assigned card should show:

- provider title
- capability badge
- availability badge
- tenant name
- compact 24h usage summary
- compact quota status
- primary action: `Manage`

### Available provider card

Each available card should show:

- provider title
- capability badge
- credential status
- optional cost metadata summary
- “No tenant assigned”
- primary action: `Assign`

## Provider Modal

### Mode A: Assign

Used when clicking `Assign` on an available provider.

Sections:

- provider identity
- credential summary
- tenant selector
- submit action

The modal should not show quota controls yet because the provider is not assigned.

### Mode B: Manage

Used when clicking `Manage` on an assigned provider.

Tabs:

- `Overview`
- `Credential`
- `Quotas`

#### Overview tab

Shows:

- provider identity
- assigned tenant
- availability
- 24h usage
- cost metadata
- optional pricing sync timestamp/source
- `Unassign` action

#### Credential tab

Shows:

- credential validation state
- last validated / updated timestamps
- masked secret presence
- update/remove actions

#### Quotas tab

Shows only metrics relevant to provider capability.

Examples:

- `llm` / `judge`: input tokens, output tokens, requests
- `tts`: characters, requests
- `stt`: audio seconds, requests

## Backend Plan

### Slice 1: Assignment contract and inventory shape

Files:

- `services/api/botcheck_api/admin/router_providers.py`
- `services/api/botcheck_api/admin/service_providers.py`
- `services/api/botcheck_api/providers/schemas.py`
- `services/api/botcheck_api/providers/service.py`
- `services/api/botcheck_api/models.py`
- migration file

Changes:

- add provider-centric assign/unassign endpoints
- enforce one-provider-to-one-tenant in service logic
- add nullable assigned-tenant object to admin provider summary response
- retain backward compatibility only where necessary during transition

Acceptance criteria:

- a provider can only be assigned to one tenant at a time
- provider list API directly reports assigned tenant name
- provider assignment can be managed without using tenant admin endpoints

### Slice 2: Page redesign

Files:

- `web/src/app/(dashboard)/admin/providers/page.tsx`
- new provider library components

Changes:

- replace two-pane layout with `Assigned` and `Available`
- remove assignment count display
- remove “tenant admin owns the rest” messaging
- make primary actions `Assign` and `Manage`

Acceptance criteria:

- admins can understand page state without selecting a row first
- assigned vs available is obvious at a glance
- each card clearly indicates the next action

### Slice 3: Provider modal

Files:

- new modal components under `web/src/components/providers/` or page-local admin provider components

Changes:

- add assign mode
- add manage mode with `Overview`, `Credential`, `Quotas`
- reuse existing usage/quota APIs where possible

Acceptance criteria:

- an available provider can be assigned from one modal flow
- an assigned provider can be managed from one modal flow
- quota editing is capability-specific and easy to understand

### Slice 4: Cost metadata and pricing suggestions

Files:

- provider/admin backend service files
- admin provider UI files

Changes:

- keep manual cost metadata editable
- optionally add “Import suggested prices” from a curated external source
- record source and sync timestamp if imported
- do not overwrite manual values silently

Acceptance criteria:

- admins can manage cost metadata without relying on a brittle external dependency
- imported prices are clearly advisory

### Slice 5: Legacy ENV migration and de-emphasis

Changes:

- reduce ENV language in the main UI
- keep fallback visible only in a diagnostic layer
- create a migration checklist for moving active env-backed providers to stored credentials

Acceptance criteria:

- primary UI reflects the intended BotCheck-managed provider model
- support/debug users can still understand fallback behavior when needed

## Pricing Strategy

### What not to assume

Do not build this feature on the assumption that OpenAI, Anthropic, Gemini, ElevenLabs, or Deepgram expose a stable machine-readable pricing API suitable as a universal source of truth.

### Recommended approach

1. Manual cost metadata stays canonical.
2. Optional external import may be added as a convenience.
3. Imported pricing must be reviewable and overrideable.
4. A future scheduled sync should only be added after the import path proves reliable in practice.

### LiteLLM position

LiteLLM pricing data is a reasonable optional suggestion source because it is broad and practical, but it is community-maintained and should not be treated as authoritative billing truth.

## Non-Goals

- redesigning tenant-facing provider selection UX in this pass
- changing provider runtime resolution semantics beyond assignment invariants
- removing ENV fallback from runtime immediately
- building a full multi-provider pricing intelligence system

## Recommended Implementation Order

1. Backend assignment invariant and provider-centric routes
2. Provider inventory response change
3. Frontend page restructure
4. Provider modal
5. Cost metadata / suggested pricing
6. ENV de-emphasis and migration cleanup

## Final Recommendation

The redesign should center provider administration around a simple sentence:

“Create a provider, assign it to one tenant, then manage that tenant’s usage and quotas.”

Everything in the backend contract and UI should reinforce that model.
