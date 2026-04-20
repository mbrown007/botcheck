import test from "node:test";
import assert from "node:assert/strict";
import { selectNodeTypeForTurn } from "../lib/node-type-selector";

test("selectNodeTypeForTurn maps bot_listen kind to botNode", () => {
  const type = selectNodeTypeForTurn({ id: "t1", kind: "bot_listen" });
  assert.equal(type, "botNode");
});

test("selectNodeTypeForTurn maps harness_prompt kind to harnessNode", () => {
  const type = selectNodeTypeForTurn({ id: "t1", kind: "harness_prompt" });
  assert.equal(type, "harnessNode");
});

test("selectNodeTypeForTurn prioritizes hangup kind", () => {
  const type = selectNodeTypeForTurn({
    id: "t1",
    kind: "hangup",
  });
  assert.equal(type, "hangupNode");
});

test("selectNodeTypeForTurn maps wait kind to waitNode", () => {
  const type = selectNodeTypeForTurn({
    id: "t1",
    kind: "wait",
  });
  assert.equal(type, "waitNode");
});

test("selectNodeTypeForTurn maps time_route kind to timeRouteNode", () => {
  const type = selectNodeTypeForTurn({
    id: "t1",
    kind: "time_route",
  });
  assert.equal(type, "timeRouteNode");
});

test("selectNodeTypeForTurn defaults missing runtime kind to harnessNode", () => {
  const type = selectNodeTypeForTurn({ id: "t1" } as never);
  assert.equal(type, "harnessNode");
});
