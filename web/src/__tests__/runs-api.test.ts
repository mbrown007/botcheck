import assert from "node:assert/strict";
import test from "node:test";
import { buildCreateRunPayload } from "../lib/api/runs";

test("buildCreateRunPayload trims scenario and dial target fields", () => {
  assert.deepEqual(
    buildCreateRunPayload(" scenario_1 ", " sip:+441234567890@example.com "),
    {
      scenario_id: "scenario_1",
      dial_target: "sip:+441234567890@example.com",
    }
  );
});

test("buildCreateRunPayload supports AI scenario and transport profile together", () => {
  assert.deepEqual(
    buildCreateRunPayload("", " +441234567890 ", " dest_123 ", " ai_delay "),
    {
      ai_scenario_id: "ai_delay",
      dial_target: "+441234567890",
      transport_profile_id: "dest_123",
    }
  );
});

test("buildCreateRunPayload omits blank optional fields", () => {
  assert.deepEqual(buildCreateRunPayload("scenario_1", "   ", "   ", "   ", "   "), {
    scenario_id: "scenario_1",
  });
});

test("buildCreateRunPayload supports ad hoc SIP trunk pools", () => {
  assert.deepEqual(
    buildCreateRunPayload(" scenario_1 ", " +441234567890 ", "", "", " pool_uk "),
    {
      scenario_id: "scenario_1",
      dial_target: "+441234567890",
      trunk_pool_id: "pool_uk",
    }
  );
});
