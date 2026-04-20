# Tenant Admin

The **Admin > Tenants** surface is the platform-level console for tenant lifecycle and tenant-specific rollout control.

## What You Can Do

- list tenants and review usage summaries
- create a new tenant
- update display name and configuration
- set tenant feature overrides
- update tenant quota overrides
- suspend or reinstate a tenant
- soft-delete a tenant with retention rather than immediate destruction

## Important Concepts

### Feature Overrides

Tenant overrides are the safest way to roll out behavior gradually.

- platform defaults still exist
- tenant overrides only affect the selected tenant
- overrides are limited to allowlisted non-secret settings

This is useful when one tenant should receive a feature early without changing the platform-wide default.

### Quotas

Quota configuration lets you shape tenant capacity for:

- concurrent runs
- runs per day
- schedules
- scenarios
- packs

### Suspension

Suspending a tenant is stronger than disabling one user:

- authentication for that tenant is blocked
- dispatch for that tenant is blocked
- data remains intact for investigation or reinstatement

Use suspension for account status issues, billing holds, or incident response.
