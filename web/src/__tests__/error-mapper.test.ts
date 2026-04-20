import test from "node:test";
import assert from "node:assert/strict";
import { ApiHttpError } from "../lib/api/fetcher";
import { mapApiError } from "../lib/api/error-mapper";

test("mapApiError with known error_code returns code-specific message and warn tone", () => {
  const body = JSON.stringify({
    type: "about:blank",
    title: "Too Many Requests",
    status: 429,
    detail: "Outbound SIP capacity exhausted; retry later",
    error_code: "sip_capacity_exhausted",
  });
  const error = new ApiHttpError("Create run failed", 429, body);
  const result = mapApiError(error);
  assert.equal(result.tone, "warn");
  assert.ok(result.message.includes("slots"), `Expected 'slots' in: ${result.message}`);
});

test("mapApiError falls back to status mapping when no error_code", () => {
  const body = JSON.stringify({
    type: "about:blank",
    title: "Forbidden",
    status: 403,
    detail: "You don't have access.",
  });
  const error = new ApiHttpError("API", 403, body);
  const result = mapApiError(error);
  assert.equal(result.tone, "error");
  assert.ok(result.message.includes("permission"), `Expected 'permission' in: ${result.message}`);
});

test("mapApiError falls back to detail string for unknown error_code and unmapped status", () => {
  // Status 418 is not in BY_STATUS, so detail should be used verbatim.
  const body = JSON.stringify({
    type: "about:blank",
    title: "I'm a Teapot",
    status: 418,
    detail: "Custom detail message",
    error_code: "unknown_custom_code",
  });
  const error = new ApiHttpError("API", 418, body);
  const result = mapApiError(error);
  assert.equal(result.message, "Custom detail message");
  assert.equal(result.tone, "error");
});

test("mapApiError with generic Error uses message and error tone", () => {
  const error = new Error("network fail");
  const result = mapApiError(error);
  assert.equal(result.message, "network fail");
  assert.equal(result.tone, "error");
});

test("mapApiError maps reaper_force_closed to warn tone", () => {
  const body = JSON.stringify({
    type: "about:blank",
    title: "Conflict",
    status: 409,
    detail: "Run force-closed by reaper",
    error_code: "reaper_force_closed",
  });
  const error = new ApiHttpError("Run update", 409, body);
  const result = mapApiError(error);
  assert.equal(result.tone, "warn");
  assert.ok(result.message.includes("force-closed"), `Expected 'force-closed' in: ${result.message}`);
});

test("mapApiError maps destination_in_use to warn tone", () => {
  const body = JSON.stringify({
    type: "about:blank",
    title: "Conflict",
    status: 409,
    detail: "Destination is in use by active schedules or active pack runs",
    error_code: "destination_in_use",
  });
  const error = new ApiHttpError("Delete destination failed", 409, body);
  const result = mapApiError(error);
  assert.equal(result.tone, "warn");
  assert.ok(result.message.includes("Destination is in use"), `Expected 'in use' in: ${result.message}`);
});

test("mapApiError maps destinations_disabled to warn tone", () => {
  const body = JSON.stringify({
    type: "about:blank",
    title: "Service Unavailable",
    status: 503,
    detail: "Destinations are disabled",
    error_code: "destinations_disabled",
  });
  const error = new ApiHttpError("Create run failed", 503, body);
  const result = mapApiError(error);
  assert.equal(result.tone, "warn");
  assert.ok(result.message.includes("Transport profiles are disabled"));
});

test("mapApiError maps destination_not_found to warn tone", () => {
  const body = JSON.stringify({
    type: "about:blank",
    title: "Not Found",
    status: 404,
    detail: "Destination not found",
    error_code: "destination_not_found",
  });
  const error = new ApiHttpError("Create run failed", 404, body);
  const result = mapApiError(error);
  assert.equal(result.tone, "warn");
  assert.ok(result.message.includes("transport profile"));
});

test("mapApiError maps job_not_found to warn tone", () => {
  const body = JSON.stringify({
    type: "about:blank",
    title: "Not Found",
    status: 404,
    detail: "Job not found",
    error_code: "job_not_found",
  });
  const error = new ApiHttpError("Load job failed", 404, body);
  const result = mapApiError(error);
  assert.equal(result.tone, "warn");
  assert.ok(result.message.includes("job"));
});

test("mapApiError maps scenario_not_found to warn tone", () => {
  const body = JSON.stringify({
    type: "about:blank",
    title: "Not Found",
    status: 404,
    detail: "Scenario not found",
    error_code: "scenario_not_found",
  });
  const error = new ApiHttpError("Load scenario failed", 404, body);
  const result = mapApiError(error);
  assert.equal(result.tone, "warn");
  assert.ok(result.message.includes("scenario"));
});

test("mapApiError maps ai_persona_not_found to warn tone", () => {
  const body = JSON.stringify({
    type: "about:blank",
    title: "Not Found",
    status: 404,
    detail: "AI persona not found",
    error_code: "ai_persona_not_found",
  });
  const error = new ApiHttpError("Load persona failed", 404, body);
  const result = mapApiError(error);
  assert.equal(result.tone, "warn");
  assert.ok(result.message.includes("persona"));
});

test("mapApiError maps pack_run_not_found to warn tone", () => {
  const body = JSON.stringify({
    type: "about:blank",
    title: "Not Found",
    status: 404,
    detail: "Pack run not found",
    error_code: "pack_run_not_found",
  });
  const error = new ApiHttpError("Load pack run failed", 404, body);
  const result = mapApiError(error);
  assert.equal(result.tone, "warn");
  assert.ok(result.message.includes("pack run"));
});

test("mapApiError maps preset_not_found to warn tone", () => {
  const body = JSON.stringify({
    type: "about:blank",
    title: "Not Found",
    status: 404,
    detail: "Playground preset not found",
    error_code: "preset_not_found",
  });
  const error = new ApiHttpError("Load preset failed", 404, body);
  const result = mapApiError(error);
  assert.equal(result.tone, "warn");
  assert.ok(result.message.includes("playground preset"));
});

test("mapApiError maps preset_name_conflict to warn tone", () => {
  const body = JSON.stringify({
    type: "about:blank",
    title: "Conflict",
    status: 409,
    detail: "Playground preset with that name already exists",
    error_code: "preset_name_conflict",
  });
  const error = new ApiHttpError("Save preset failed", 409, body);
  const result = mapApiError(error);
  assert.equal(result.tone, "warn");
  assert.ok(result.message.includes("already exists"));
});

test("mapApiError maps preset_invalid_transport_profile to warn tone", () => {
  const body = JSON.stringify({
    type: "about:blank",
    title: "HTTP 422",
    status: 422,
    detail: "Transport profile must be an active HTTP transport profile",
    error_code: "preset_invalid_transport_profile",
  });
  const error = new ApiHttpError("Save preset failed", 422, body);
  const result = mapApiError(error);
  assert.equal(result.tone, "warn");
  assert.ok(result.message.includes("HTTP transport profile"));
});

test("mapApiError maps recording_not_found to warn tone", () => {
  const body = JSON.stringify({
    type: "about:blank",
    title: "Not Found",
    status: 404,
    detail: "Recording not found",
    error_code: "recording_not_found",
  });
  const error = new ApiHttpError("Download recording failed", 404, body);
  const result = mapApiError(error);
  assert.equal(result.tone, "warn");
  assert.ok(result.message.includes("Recording"));
});

test("mapApiError maps ai_scenario_dispatch_unavailable to warn tone", () => {
  const body = JSON.stringify({
    type: "about:blank",
    title: "Service Unavailable",
    status: 503,
    detail: "AI scenario dispatch is not available yet",
    error_code: "ai_scenario_dispatch_unavailable",
  });
  const error = new ApiHttpError("Create run failed", 503, body);
  const result = mapApiError(error);
  assert.equal(result.tone, "warn");
  assert.ok(
    result.message.includes("AI scenario dispatch is not available yet"),
    `Expected AI dispatch message, got: ${result.message}`
  );
});

test("mapApiError maps ai_caller_unavailable to warn tone", () => {
  const body = JSON.stringify({
    type: "about:blank",
    title: "Service Unavailable",
    status: 503,
    detail: "AI caller runtime is unavailable for this run",
    error_code: "ai_caller_unavailable",
  });
  const error = new ApiHttpError("Run failed", 503, body);
  const result = mapApiError(error);
  assert.equal(result.tone, "warn");
  assert.ok(
    result.message.includes("AI caller runtime is unavailable"),
    `Expected AI caller message, got: ${result.message}`
  );
});

test("mapApiError maps tts_cache_unavailable to warn tone", () => {
  const body = JSON.stringify({
    type: "about:blank",
    title: "Conflict",
    status: 409,
    detail: "Scenario requires prewarmed TTS cache before dispatch",
    error_code: "tts_cache_unavailable",
  });
  const error = new ApiHttpError("Create run failed", 409, body);
  const result = mapApiError(error);
  assert.equal(result.tone, "warn");
  assert.ok(
    result.message.includes("TTS cache is not ready"),
    `Expected cache message, got: ${result.message}`
  );
});
