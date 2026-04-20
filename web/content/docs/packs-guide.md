# Scenario Packs

Scenario Packs are collections of scenarios that you can run together as a single unit. They are the primary tool for regression testing and CI/CD gating.

## Benefits of Using Packs

- **Batch Testing:** Group scenarios by logical sets (e.g., "Smoke Tests," "Security Audit," "Billing Regressions").
- **Speed:** Execute scenarios in a pack in parallel.
- **Unified Results:** See the aggregate pass/fail rate for the entire pack.

## Managing Your Packs

### 1. Adding Scenarios
Select from existing **Graph** and **AI Scenarios** to build your pack. You can also reorder them as needed.

### 2. Execution Mode
By default, packs run scenarios in **Parallel**. You can adjust the concurrency limit in the pack settings to avoid hitting provider rate limits.

### 3. Pack Runs
When you run a pack, a **Pack Run** is created. 
- **The Heatmap:** A visual summary of the pack's performance across all scenarios.
- **Failure Analysis:** Quickly identify which scenarios in the pack failed and why.
- **Trend Data:** Compare current pack results with previous runs to spot regressions.

## Running Packs via API
Packs are designed to be triggered from your CI/CD pipelines (e.g., GitHub Actions, GitLab CI). Each pack has a unique ID and endpoint for manual or automated execution.
