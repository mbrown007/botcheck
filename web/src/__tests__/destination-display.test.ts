import assert from "node:assert/strict";
import test from "node:test";
import {
  describeTransportDispatch,
  destinationLabelForId,
  destinationNameMap,
  findTransportProfile,
  transportProfileOptionLabel,
} from "../lib/destination-display";

const destinations = [
  {
    destination_id: " dest_primary ",
    transport_profile_id: " profile_primary ",
    name: " Primary SIP ",
    protocol: "sip" as const,
    endpoint: "sip:1000@example.com",
    default_dial_target: "sip:1000@example.com",
    effective_channels: 3,
    is_active: true,
    created_at: "2026-03-05T00:00:00Z",
    updated_at: "2026-03-05T00:00:00Z",
  },
  {
    destination_id: "dest_empty_name",
    transport_profile_id: "dest_empty_name",
    name: "   ",
    protocol: "mock" as const,
    endpoint: null,
    default_dial_target: null,
    is_active: true,
    created_at: "2026-03-05T00:00:00Z",
    updated_at: "2026-03-05T00:00:00Z",
  },
  {
    destination_id: "dest_http",
    transport_profile_id: "dest_http",
    name: "Direct Bot API",
    protocol: "http" as const,
    endpoint: "https://bot.internal/chat",
    default_dial_target: "https://bot.internal/chat",
    is_active: true,
    created_at: "2026-03-05T00:00:00Z",
    updated_at: "2026-03-05T00:00:00Z",
  },
];

test("destinationNameMap normalizes names keyed by both legacy and transport profile ids", () => {
  const names = destinationNameMap(destinations);

  assert.deepEqual(names, {
    dest_primary: "Primary SIP",
    profile_primary: "Primary SIP",
    dest_empty_name: "dest_empty_name",
    dest_http: "Direct Bot API",
  });
});

test("destinationLabelForId returns name + id label when known", () => {
  assert.equal(
    destinationLabelForId("dest_primary", { dest_primary: "Primary SIP" }),
    "Primary SIP (dest_primary)"
  );
});

test("destinationLabelForId falls back to id for unknown ids", () => {
  assert.equal(destinationLabelForId("dest_unknown", {}), "dest_unknown");
  assert.equal(destinationLabelForId("  ", {}), null);
});

test("findTransportProfile matches both legacy and canonical ids", () => {
  assert.equal(
    findTransportProfile(destinations, "profile_primary")?.destination_id.trim(),
    "dest_primary"
  );
  assert.equal(
    findTransportProfile(destinations, "dest_primary")?.transport_profile_id.trim(),
    "profile_primary"
  );
  assert.equal(findTransportProfile(destinations, "missing"), null);
});

test("transportProfileOptionLabel includes protocol and channel context", () => {
  assert.equal(transportProfileOptionLabel(destinations[0]), "Primary SIP · SIP · 3ch");
  assert.equal(transportProfileOptionLabel(destinations[2]), "Direct Bot API · HTTP");
});

test("describeTransportDispatch explains profile default target fallback", () => {
  assert.equal(
    describeTransportDispatch({
      destinations,
      transportProfileId: "profile_primary",
      dialTarget: "",
      fallbackTargetLabel: "scenario endpoint",
    }),
    "Will use Primary SIP's default dial target: sip:1000@example.com."
  );
});

test("describeTransportDispatch explains transport-only profile fallback", () => {
  assert.equal(
    describeTransportDispatch({
      destinations,
      transportProfileId: "dest_empty_name",
      dialTarget: "",
      fallbackTargetLabel: "scenario endpoint",
    }),
    "This transport profile has no default dial target. If left blank, the scenario endpoint will be used."
  );
});

test("describeTransportDispatch explains explicit dial target override", () => {
  assert.equal(
    describeTransportDispatch({
      destinations,
      transportProfileId: "profile_primary",
      dialTarget: "+447700900123",
      fallbackTargetLabel: "scenario endpoint",
    }),
    "Will dial +447700900123 via Primary SIP."
  );
});

test("describeTransportDispatch explains http profile endpoint behavior", () => {
  assert.equal(
    describeTransportDispatch({
      destinations,
      transportProfileId: "dest_http",
      dialTarget: "",
      fallbackTargetLabel: "scenario endpoint",
    }),
    "Will use Direct Bot API's default endpoint: https://bot.internal/chat."
  );
  assert.equal(
    describeTransportDispatch({
      destinations,
      transportProfileId: "dest_http",
      dialTarget: "https://override.internal/chat",
      fallbackTargetLabel: "scenario endpoint",
    }),
    "Will send requests to https://override.internal/chat via Direct Bot API."
  );
});
