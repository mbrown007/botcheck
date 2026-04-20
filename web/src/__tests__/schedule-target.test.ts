import assert from "node:assert/strict";
import test from "node:test";
import {
  formatScheduleTargetLabel,
  scheduleBotEndpointOverride,
  scheduleDestinationOverrideId,
} from "../lib/schedule-target";

test("formatScheduleTargetLabel renders scenario and pack labels", () => {
  assert.equal(
    formatScheduleTargetLabel({
      target_type: "scenario",
      scenario_id: "scenario-a",
      ai_scenario_id: null,
      pack_id: null,
      config_overrides: null,
    }),
    "scenario:scenario-a · GRAPH"
  );
  assert.equal(
    formatScheduleTargetLabel({
      target_type: "scenario",
      scenario_id: "scenario-ai-backing",
      ai_scenario_id: "flight-delay-parent",
      pack_id: null,
      config_overrides: null,
    }),
    "scenario:flight-delay-parent · AI"
  );
  assert.equal(
    formatScheduleTargetLabel({
      target_type: "pack",
      scenario_id: null,
      ai_scenario_id: null,
      pack_id: "pack-a",
      config_overrides: null,
    }),
    "pack:pack-a"
  );
});

test("scheduleDestinationOverrideId returns destination override for scenario target", () => {
  assert.equal(
    scheduleDestinationOverrideId({
      target_type: "scenario",
      scenario_id: "scenario-a",
      ai_scenario_id: null,
      pack_id: null,
      config_overrides: { destination_id: "dest_primary" },
    }),
    "dest_primary"
  );
});

test("scheduleDestinationOverrideId prefers transport profile override when present", () => {
  assert.equal(
    scheduleDestinationOverrideId({
      target_type: "scenario",
      scenario_id: "scenario-a",
      ai_scenario_id: null,
      pack_id: null,
      config_overrides: {
        destination_id: "dest_primary",
        transport_profile_id: "profile_primary",
      },
    }),
    "profile_primary"
  );
});

test("scheduleDestinationOverrideId ignores missing/blank overrides", () => {
  assert.equal(
    scheduleDestinationOverrideId({
      target_type: "scenario",
      scenario_id: "scenario-a",
      ai_scenario_id: null,
      pack_id: null,
      config_overrides: null,
    }),
    null
  );
  assert.equal(
    scheduleDestinationOverrideId({
      target_type: "scenario",
      scenario_id: "scenario-a",
      ai_scenario_id: null,
      pack_id: null,
      config_overrides: { destination_id: "   " },
    }),
    null
  );
});

test("scheduleDestinationOverrideId supports pack target overrides", () => {
  assert.equal(
    scheduleDestinationOverrideId({
      target_type: "pack",
      scenario_id: null,
      ai_scenario_id: null,
      pack_id: "pack-a",
      config_overrides: { destination_id: "dest_primary" },
    }),
    "dest_primary"
  );
});

test("scheduleBotEndpointOverride returns trimmed bot endpoint override", () => {
  assert.equal(
    scheduleBotEndpointOverride({
      target_type: "scenario",
      scenario_id: "scenario-a",
      ai_scenario_id: null,
      pack_id: null,
      config_overrides: { bot_endpoint: " sip:07785766172@sipgate.co.uk " },
    }),
    "sip:07785766172@sipgate.co.uk"
  );
});

test("scheduleBotEndpointOverride prefers dial_target when present", () => {
  assert.equal(
    scheduleBotEndpointOverride({
      target_type: "scenario",
      scenario_id: "scenario-a",
      ai_scenario_id: null,
      pack_id: null,
      config_overrides: {
        bot_endpoint: "sip:legacy@example.com",
        dial_target: " +447785766172 ",
      },
    }),
    "+447785766172"
  );
});

test("formatScheduleTargetLabel resolves AI kind via aiScenarioIds cross-reference", () => {
  const aiIds = new Set(["scenario-a"]);
  assert.equal(
    formatScheduleTargetLabel(
      {
        target_type: "scenario",
        scenario_id: "scenario-a",
        ai_scenario_id: null,
        pack_id: null,
        config_overrides: null,
      },
      aiIds
    ),
    "scenario:scenario-a · AI"
  );
  assert.equal(
    formatScheduleTargetLabel(
      {
        target_type: "scenario",
        scenario_id: "scenario-b",
        ai_scenario_id: null,
        pack_id: null,
        config_overrides: null,
      },
      aiIds
    ),
    "scenario:scenario-b · GRAPH"
  );
});

test("scheduleBotEndpointOverride ignores missing or blank overrides", () => {
  assert.equal(
    scheduleBotEndpointOverride({
      target_type: "scenario",
      scenario_id: "scenario-a",
      ai_scenario_id: null,
      pack_id: null,
      config_overrides: null,
    }),
    null
  );
  assert.equal(
    scheduleBotEndpointOverride({
      target_type: "scenario",
      scenario_id: "scenario-a",
      ai_scenario_id: null,
      pack_id: null,
      config_overrides: { bot_endpoint: "   " },
    }),
    null
  );
});
