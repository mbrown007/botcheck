import assert from "node:assert/strict";
import test from "node:test";
import {
  buildScenarioCacheTurnLookup,
  scenarioCacheCoverageLabel,
  scenarioCacheObjectPath,
} from "@/lib/scenario-cache";
import type { ScenarioCacheStateResponse } from "@/lib/api/types";

function makeState(): ScenarioCacheStateResponse {
  return {
    scenario_id: "scenario-a",
    scenario_version_hash: "v1",
    cache_status: "partial",
    cached_turns: 1,
    skipped_turns: 1,
    failed_turns: 1,
    total_harness_turns: 3,
    updated_at: null,
    bucket_name: "botcheck-artifacts",
    turn_states: [
      { turn_id: "t1", status: "cached", key: "default/tts-cache/t1/hash.wav" },
      { turn_id: "t2", status: "failed", key: "default/tts-cache/t2/hash.wav" },
    ],
  };
}

test("buildScenarioCacheTurnLookup indexes turn state by turn id", () => {
  const lookup = buildScenarioCacheTurnLookup(makeState());
  assert.deepEqual(lookup.t1, {
    status: "cached",
    key: "default/tts-cache/t1/hash.wav",
  });
  assert.deepEqual(lookup.t2, {
    status: "failed",
    key: "default/tts-cache/t2/hash.wav",
  });
});

test("scenarioCacheObjectPath returns full s3 path when bucket is present", () => {
  assert.equal(
    scenarioCacheObjectPath("botcheck-artifacts", "default/tts-cache/t1/hash.wav"),
    "s3://botcheck-artifacts/default/tts-cache/t1/hash.wav"
  );
});

test("scenarioCacheObjectPath falls back to raw key when bucket is absent", () => {
  assert.equal(
    scenarioCacheObjectPath(null, "default/tts-cache/t1/hash.wav"),
    "default/tts-cache/t1/hash.wav"
  );
});

test("scenarioCacheCoverageLabel returns cached coverage summary", () => {
  assert.equal(scenarioCacheCoverageLabel(makeState()), "2/3");
});
