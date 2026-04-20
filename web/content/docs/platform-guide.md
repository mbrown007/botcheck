# Platform Guide

Welcome to the BotCheck Platform Guide. This document provides a comprehensive overview of how to use BotCheck to evaluate, monitor, and secure your voicebot applications.

## Table of Contents

- [Core Concepts](#core-concepts)
- [User Guide](#user-guide)
  - [Scenario Builder](#scenario-builder)
  - [AI Scenarios](#ai-scenarios)
  - [Managing Runs](#managing-runs)
  - [Packs and Regression Testing](#packs-and-regression-testing)
  - [Schedules](#schedules)
- [Administrator Guide](#administrator-guide)
  - [Admin Surfaces](#admin-surfaces)
  - [User & Tenant Management](#user--tenant-management)
  - [SIP Trunk Configuration](#sip-trunk-configuration)
  - [Audit Logs](#audit-logs)
- [Reference](#reference)
  - [Scenario YAML DSL](#scenario-yaml-dsl)
  - [Scoring Rubrics](#scoring-rubrics)

---

## Core Concepts

BotCheck is an automated evaluation platform for voicebots. It works by acting as a **Harness** (a synthetic caller) that interacts with your bot over SIP or WebRTC, and then uses an LLM-based **Judge** to score the resulting conversation against a predefined **Scenario**.

- **Harness:** The execution agent that "calls" the bot. It handles TTS (Text-to-Speech), ASR (Automatic Speech Recognition), and media transport.
- **Judge:** The evaluation service that analyzes the transcript and audio to determine if the bot met the scenario's expectations.
- **Scenario:** A YAML definition of a conversation, including what the harness says and what the bot is expected to do.
- **Run:** A single execution of a scenario.
- **Pack:** A collection of scenarios run together, often used for regression testing.

---

## User Guide

### Scenario Builder

The Scenario Builder is a visual tool for authoring "Graph" scenarios. It allows you to map out complex multi-turn conversations with branching logic.

1. **Nodes:** Represent harness turns or bot expectations.
2. **Edges:** Define the flow of the conversation based on bot responses or branching conditions.
3. **Validation:** The builder ensures your graph is logical and has a valid "Golden Path."

### AI Scenarios

AI Scenarios use an "Intent-first" approach. Instead of a rigid graph, you define a **Persona** and a **Goal** for the Harness, and the Harness uses an LLM to interact dynamically with your bot.

- **Authoring:** Define the "Brief," "Facts," and "Objective."
- **Evaluation:** The Judge evaluates if the objective was met, even if the conversation took an unpredictable path.

### Managing Runs

Every time you execute a scenario, a **Run** is created. 

- **Live Monitoring:** Watch the transcript and listen to the audio in real-time as the Harness interacts with the bot.
- **Results:** After the call ends, the Judge provides a detailed report with scores, findings, and reasoning.
- **Gate Result:** If a run is part of a CI/CD pipeline, it will show a "Passed" or "Blocked" status based on your scoring thresholds.

### Packs and Regression Testing

Packs allow you to group scenarios into logical sets (e.g., "Smoke Tests," "Security Audit," "Billing Regressions").

- **Parallel Execution:** BotCheck can run multiple scenarios in a pack simultaneously to save time.
- **Aggregate Reporting:** View the overall "Pass/Fail" rate for the entire pack.

### Schedules

Automate your testing by scheduling Pack runs.

- **Cron Expressions:** Use standard cron syntax to run tests hourly, daily, or weekly.
- **Targeting:** Schedules can target specific SIP trunks or transport profiles to test different environments.

---

## Administrator Guide

### Admin Surfaces

BotCheck exposes administrative workflows through the authenticated web admin surfaces and matching admin API endpoints.

- **User Admin:** create users, reset passwords, revoke sessions, and reset 2FA
- **Tenant Admin:** manage tenant lifecycle, overrides, and quotas
- **System Admin:** review platform health and persisted feature defaults
- **SIP Admin:** inspect and sync SIP trunk inventory

### User & Tenant Management

BotCheck supports multi-tenancy. Admin tasks include:

- **Creating Users:** Add new operators and assign roles (admin, operator, viewer).
- **Managing Tenants:** Setup new tenant IDs and partition data.
- **Password Resets:** Securely reset user passwords from the admin user-management surface.

### SIP Trunk Configuration

Manage the telephony infrastructure used by the Harness.

- **Sync with LiveKit:** Use the SIP admin surface to synchronize outbound SIP trunk inventory from your LiveKit backend.
- **Trunk Metadata:** View and verify the active numbers and providers associated with your trunks.

### Audit Logs

Track all administrative and high-level operational actions.

- **Visibility:** View who performed what action, when, and on which resource (e.g., "User X updated Scenario Y").
- **Compliance:** Audit logs are preserved in the database for security and compliance reviews.

---

## Reference

### Scenario YAML DSL

Scenarios can be authored directly in YAML for advanced use cases.

```yaml
version: "1.0"
id: simple-smoke-test
name: "Simple Smoke Test"
type: golden_path
bot:
  endpoint: "sip:bot@example.com"
  protocol: sip
turns:
  - id: t1
    text: "Hello, I'd like to check my balance."
    expect:
      intent_recognized: true
```

### Scoring Rubrics

Define how your scenarios are graded by customizing the `scoring` section in your YAML.

- **Dimensions:** `routing`, `policy`, `jailbreak`, `pii_handling`, `reliability`.
- **Thresholds:** Set the minimum score required for a "Pass" status.
- **CI Gating:** Specify which dimensions are critical enough to block a deployment.
