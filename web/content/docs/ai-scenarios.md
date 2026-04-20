# AI Scenarios (Intent Editor)

AI Scenarios represent a new, intent-driven approach to testing. Instead of a hardcoded graph, you define the "persona" and "goal" of the harness, and it uses an LLM to interact dynamically with your voicebot.

## Why Use AI Scenarios?

- **Unpredictable Behavior:** Test how your bot handles unexpected or complex human interaction.
- **Natural Conversations:** Avoid "rigid" scripts that bots might be tuned to handle too well.
- **Red Teaming:** Automate the probing of bot boundaries, PII leaks, and jailbreaks.

## Configuring an AI Scenario

### 1. The Brief (Harness Goals)
Describe what the harness (the caller) is trying to achieve. For example: *"Call the billing department and try to get a late fee waived by complaining about service quality."*

### 2. Facts and Context
Provide the harness with any necessary background information (e.g., account numbers, service dates, or emotional state like *"frustrated"*).

### 3. Evaluation Objectives
Define what the Judge should look for to determine a successful run.
- **Primary Goal:** Did the harness achieve its objective?
- **Policy Compliance:** Did the bot follow internal rules?

## Working with Personas

AI Scenarios are linked to a **Persona**. You can select from templates (e.g., "The Impatient Caller," "The Tech-Savvy Senior") or create your own custom persona to test specific demographics.

## Evaluation Records (Test Data)
AI scenarios can include **Scenario Records**, which act as baseline "Gold Answers." These provide the Judge with high-quality reference points for the expected bot interaction.

## Speech and Runtime Overrides
Like Graph scenarios, AI scenarios allow you to override the **TTS Voice**, **STT Provider**, and **Language** to test regional variations or provider-specific latency.
