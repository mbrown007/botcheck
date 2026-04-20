# Administration and Setup

The **Administration** dashboard is used to manage the platform's infrastructure and security settings.

## Admin Surface Map

- [User Admin](/docs/admin-users) for user lifecycle, password resets, 2FA reset, and session revocation
- [Tenant Admin](/docs/admin-tenants) for tenant lifecycle, overrides, quotas, and suspension
- [System Admin](/docs/admin-system) for platform health, feature defaults, and quota defaults
- [SIP Admin](/docs/admin-sip) for SIP trunk inventory and sync operations
- [Audit Logs](/docs/audit-logs) for review of administrative and operational events

## Managing Users

As an administrator, you can manage the users on your BotCheck instance:

### 1. Adding New Users
Create a new user by providing their email address and assigning a **Role** (e.g., admin, operator, or viewer).

### 2. Password Resets
Administrators can securely reset user passwords from the **Admin > Users** surface, which also revokes active sessions as part of the recovery flow.

### 3. Toggling Status
Quickly enable or disable a user's account to control access without deleting their history.

## Tenancy and Organization
BotCheck is designed with multi-tenancy at its core. You can partition your data and users by **Tenant ID**, ensuring that scenarios and runs are isolated between different departments or clients.

## System Configuration and Flags
Platform administrators can manage persisted platform defaults and rollout flags from the **Admin > System** surface.

## Telephony Infrastructure
View and verify the **SIP Trunks** used by the Harness agent. 
- **Active Numbers:** See which phone numbers are currently assigned to your trunks.
- **Registry Sync:** Use **Admin > SIP** to trigger a trunk inventory sync against LiveKit.
- **Provider Status:** Monitor the status of your connection to telephony providers like LiveKit.
