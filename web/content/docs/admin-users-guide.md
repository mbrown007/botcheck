# User Admin

The **Admin > Users** surface is the tenant-scoped console for managing operator accounts and access recovery.

## What You Can Do

- create a user directly with an assigned role
- update user email and role
- lock and unlock accounts
- reset passwords
- reset 2FA enrollment
- revoke all active sessions for a user

## Role Scope

- tenant admins can manage users within their own tenant
- platform admins can access the same surface with broader scope when needed
- all actions are tied to the authenticated actor and written to the audit log

## Operational Notes

### Creating Users

When you create a user, choose the lowest role that fits the job:

- `viewer` for read-only monitoring
- `operator` for run operations
- `editor` for scenario and schedule authoring
- `admin` for tenant administration

### Password and 2FA Recovery

Password reset and 2FA reset actions are security-sensitive:

- active sessions are invalidated
- the recovery action is audit logged
- the user must authenticate again after recovery

### Locking and Unlocking

Locking a user is useful when:

- an account should be temporarily disabled
- suspicious behavior needs investigation
- an operator has left the team but deletion is not appropriate

Unlocking restores access without losing history.
