# SIP Admin

The **Admin > SIP** surface is the telephony operations view for trunk inventory and registry synchronization.

## What It Shows

- known SIP trunks
- provider metadata
- active numbers
- sync status and last refresh state

## Syncing Trunks

The **Sync Trunks** action refreshes the stored registry from the LiveKit-backed telephony inventory.

Use it when:

- a new trunk has been provisioned
- numbers have changed
- you need to confirm what the platform believes is currently active

## Operational Guidance

### Before Sync

- confirm platform credentials are healthy
- confirm you are acting from a platform-admin account

### After Sync

- verify expected trunks are present
- verify assigned numbers look correct
- verify the downstream transport/profile setup still maps to the expected telephony inventory

## Scope Boundary

SIP admin is a platform surface, not a tenant-authored configuration area. Tenant operators should generally work with transport profiles and schedules rather than trunk inventory directly.
