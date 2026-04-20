import test from "node:test";
import assert from "node:assert/strict";
import YAML from "yaml";
import {
  buildAiBackingScenarioId,
  buildAiBackingScenarioYaml,
  deriveAiScenarioPublicId,
  parseAiScenarioFactsText,
} from "../lib/ai-scenario-authoring";

test("deriveAiScenarioPublicId slugifies the explicit id when present", () => {
  assert.equal(
    deriveAiScenarioPublicId("Delayed Flight", " Delay Ryanair  "),
    "delay-ryanair"
  );
});

test("deriveAiScenarioPublicId falls back to the name", () => {
  assert.equal(
    deriveAiScenarioPublicId("Enquire About Delayed Flight Booking"),
    "enquire-about-delayed-flight-booking"
  );
});

test("buildAiBackingScenarioId derives a hidden runtime id", () => {
  assert.equal(
    buildAiBackingScenarioId("delay-ryanair", "ABC-123"),
    "ai-runtime-delay-ryanair-abc123"
  );
});

test("parseAiScenarioFactsText accepts blank input", () => {
  assert.deepEqual(parseAiScenarioFactsText("   "), {});
});

test("parseAiScenarioFactsText parses a json object", () => {
  assert.deepEqual(parseAiScenarioFactsText('{ "booking_ref": "ABC123" }'), {
    booking_ref: "ABC123",
  });
});

test("parseAiScenarioFactsText rejects arrays", () => {
  assert.throws(() => parseAiScenarioFactsText('["bad"]'), {
    message: "Structured facts must be a JSON object.",
  });
});

test("buildAiBackingScenarioYaml emits a valid minimal backing scenario", () => {
  const yaml = buildAiBackingScenarioYaml({
    scenarioId: "ai-runtime-delay-ryanair-abc123",
    name: "Delayed Flight Support",
    description: "Internal backing scenario",
  });
  const parsed = YAML.parse(yaml) as Record<string, unknown>;
  assert.equal(parsed.id, "ai-runtime-delay-ryanair-abc123");
  assert.equal(parsed.type, "golden_path");
  assert.equal((parsed.bot as { protocol: string }).protocol, "mock");
  assert.equal(
    (((parsed.turns as Array<{ content?: { text?: string } }>)[0] || {}).content || {}).text,
    "AI runtime placeholder turn."
  );
});
