# AI Personas

AI Personas define the "identity" of the synthetic caller (the harness) used in **AI Scenarios**.

## Customizing Personas

When you create or edit a persona, you can configure several key attributes:

### 1. The Persona Brief
This is the internal "System Prompt" for the harness. It describes who the caller is, their background, and their behavior (e.g., *"A polite but persistent customer who has been waiting for a refund for two weeks"*).

### 2. Mood and Style
- **Mood:** Set the emotional state (e.g., neutral, annoyed, apologetic).
- **Style:** Define the response style (e.g., concise, verbose, technical).

### 3. Voice Identity
Link the persona to a specific **TTS Voice** (e.g., an ElevenLabs voice ID or an OpenAI voice like `nova`). This ensures the persona always "sounds" consistent across different AI scenarios.

## Using Personas in Scenarios

Personas are reusable across multiple AI Scenarios. By changing a persona's configuration, you can quickly re-test your voicebot against a different "type" of caller (e.g., changing from a calm caller to an angry one).

## Persona Templates
The platform provides several default templates that you can use as starting points or as baseline benchmarks for your bot's behavior.
