# Automated Schedules

Schedules allow you to automate the execution of your **Scenario Packs** and individual **Scenarios** at regular intervals.

## Why Automate with Schedules?

- **Continuous Monitoring:** Run smoke tests hourly or daily to ensure your voicebot is always available.
- **Regression Gating:** Regularly test your entire suite of scenarios to catch regression bugs early.
- **Environment Verification:** Test your bot's behavior in different environments (e.g., test, staging, production) automatically.

## Configuring a Schedule

### 1. The Target
Select either a single **Scenario** or a **Scenario Pack** to run.

### 2. Cron Expression
BotCheck uses standard cron syntax to define the schedule.
- **Example:** `0 * * * *` runs every hour at the top of the hour.
- **Example:** `0 0 * * *` runs every day at midnight.

### 3. Transport Profiles
Assign a **Transport Profile** (e.g., SIP or WebRTC) to the schedule. This defines how the Harness will connect to the bot for each automated run.

### 4. Active/Inactive Toggle
You can quickly enable or disable a schedule without deleting it. This is useful for temporary environment maintenance or during rollout periods.

## Schedule History and Notifications
View the history of all runs triggered by a schedule. Each run is linked back to the original schedule for easy tracking and troubleshooting.
