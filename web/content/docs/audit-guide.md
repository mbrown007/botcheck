# Audit Logs

The **Audit Logs** dashboard provides a comprehensive history of all administrative and high-level operational actions performed on your BotCheck instance.

## Tracking Actions

Every time a user performs a key action, a new record is created in the audit log.
- **Actor:** The user ID of the person who performed the action.
- **Action:** The type of action (e.g., `create_user`, `update_scenario`, `delete_pack`).
- **Resource:** The ID of the resource affected (e.g., scenario ID or pack ID).
- **Timestamp:** The exact time the action occurred.

## Searching the Log
Filter the audit log by:
- **Tenant ID:** Narrow your search to a specific tenant.
- **Action Type:** Find all occurrences of a specific action.
- **Date Range:** Focus on a particular timeframe.

## Compliance and Security
Audit logs are immutable and preserved in the database for security and compliance reviews. They provide the "who, what, and when" for all system-level changes, ensuring accountability across your organization.
