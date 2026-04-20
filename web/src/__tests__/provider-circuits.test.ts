import test from "node:test";
import assert from "node:assert/strict";
import {
  providerCircuitAgeLabel,
  providerCircuitBadgeVariant,
  sortProviderCircuits,
} from "../lib/provider-circuits";
import type { ProviderCircuitState } from "../lib/api/types";

function makeCircuit(
  partial: Partial<ProviderCircuitState> & Pick<ProviderCircuitState, "component">
): ProviderCircuitState {
  return {
    source: partial.source ?? "agent",
    provider: partial.provider ?? "openai",
    service: partial.service ?? "tts",
    component: partial.component,
    state: partial.state ?? "closed",
    updated_at: partial.updated_at ?? null,
  };
}

test("providerCircuitBadgeVariant maps states to badge variants", () => {
  assert.equal(providerCircuitBadgeVariant("open"), "fail");
  assert.equal(providerCircuitBadgeVariant("half_open"), "warn");
  assert.equal(providerCircuitBadgeVariant("closed"), "pass");
  assert.equal(providerCircuitBadgeVariant("unknown"), "pending");
});

test("providerCircuitAgeLabel renders duration labels from timestamps", () => {
  const nowMs = Date.parse("2026-01-01T00:10:00Z");
  assert.equal(providerCircuitAgeLabel("2026-01-01T00:09:40Z", nowMs), "20s ago");
  assert.equal(providerCircuitAgeLabel("2026-01-01T00:08:00Z", nowMs), "2m ago");
  assert.equal(providerCircuitAgeLabel("2026-01-01T00:00:00Z", nowMs), "10m ago");
});

test("providerCircuitAgeLabel handles missing or invalid timestamps", () => {
  assert.equal(providerCircuitAgeLabel(null), "no signal");
  assert.equal(providerCircuitAgeLabel("not-a-date"), "invalid timestamp");
});

test("sortProviderCircuits sorts by state severity then deterministic identity", () => {
  const circuits: ProviderCircuitState[] = [
    makeCircuit({ source: "judge", component: "judge_tts", state: "closed" }),
    makeCircuit({ source: "agent", component: "agent_tts", state: "open" }),
    makeCircuit({ source: "api", component: "preview_tts", state: "half_open" }),
    makeCircuit({ source: "agent", component: "agent_fallback", state: "open" }),
  ];

  const sorted = sortProviderCircuits(circuits);
  assert.deepEqual(
    sorted.map((circuit) => `${circuit.state}:${circuit.source}:${circuit.component}`),
    [
      "open:agent:agent_fallback",
      "open:agent:agent_tts",
      "half_open:api:preview_tts",
      "closed:judge:judge_tts",
    ]
  );
});
