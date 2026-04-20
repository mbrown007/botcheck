# System Admin

The **Admin > System** surface is the platform-wide control plane for health, rollout defaults, and quota defaults.

## Main Areas

### Health

The health view is the quickest way to understand platform state across:

- database
- Redis and worker dependencies
- LiveKit integration
- provider readiness snapshots

### Feature Defaults

Platform defaults define the baseline behavior for all tenants.

- they are persisted rather than in-memory toggles
- tenant overrides can still layer on top
- secrets are not editable from this surface

Use this page when you need to change rollout defaults without redeploying application code.

### Quota Defaults

Quota defaults define the baseline tenant capacity before any tenant-specific override is applied.

This helps operations teams standardize the starting limits for new tenants while still allowing exceptions where justified.

## Recommended Use

Use **System Admin** for:

- rollout coordination
- incident visibility
- platform default changes
- sanity-checking what the effective control-plane defaults are

Do not use it as a replacement for tenant-specific override management when only one tenant should change.
