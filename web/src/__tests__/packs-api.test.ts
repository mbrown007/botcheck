import assert from "node:assert/strict";
import test from "node:test";
import { buildRunPackDispatchRequest } from "../lib/api/packs";

test("buildRunPackDispatchRequest sets idempotency header when provided", () => {
  const request = buildRunPackDispatchRequest(
    { Authorization: "Bearer token" },
    { idempotencyKey: " idem-123 " }
  );
  assert.equal(request.headers.get("Authorization"), "Bearer token");
  assert.equal(request.headers.get("Idempotency-Key"), "idem-123");
  assert.equal(request.body, undefined);
});

test("buildRunPackDispatchRequest sets transport profile payload and content type", () => {
  const request = buildRunPackDispatchRequest(
    { Authorization: "Bearer token" },
    { transportProfileId: " dest_abc " }
  );
  assert.equal(request.headers.get("Content-Type"), "application/json");
  assert.equal(request.body, JSON.stringify({ transport_profile_id: "dest_abc" }));
});

test("buildRunPackDispatchRequest supports idempotency, transport profile, and dial target together", () => {
  const request = buildRunPackDispatchRequest(
    { Authorization: "Bearer token" },
    {
      idempotencyKey: "idem-999",
      transportProfileId: "dest_primary",
      dialTarget: "+441234567890",
    }
  );
  assert.equal(request.headers.get("Idempotency-Key"), "idem-999");
  assert.equal(request.headers.get("Content-Type"), "application/json");
  assert.equal(
    request.body,
    JSON.stringify({
      transport_profile_id: "dest_primary",
      dial_target: "+441234567890",
    })
  );
});
