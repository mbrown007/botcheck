import test from "node:test";
import assert from "node:assert/strict";
import { useBuilderStore } from "../lib/builder-store";
import { flowToYaml } from "../lib/flow-translator";

const BASE_YAML = `version: "1.0"
id: store-smoke
name: Store Smoke
type: reliability
description: store smoke scenario
bot:
  endpoint: sip:test@example.com
  protocol: sip
persona:
  mood: neutral
  response_style: formal
config:
  max_total_turns: 8
scoring:
  overall_gate: false
  rubric: []
tags: []
turns:
  - id: t1
    kind: harness_prompt
    content:
      text: hello
    listen: true
`;

test("builder store hydrates and resets dirty state", () => {
  useBuilderStore.getState().reset();
  useBuilderStore.getState().hydrateFromYaml(BASE_YAML);
  const state = useBuilderStore.getState();
  assert.equal(state.nodes.length, 1);
  assert.equal(state.isDirty, false);
  assert.equal(state.parseError, null);
  assert.equal(state.yamlDraft, state.yamlCanonical);
});

test("setYamlDraft marks dirty and applyYamlDraft commits valid draft", () => {
  useBuilderStore.getState().reset();
  useBuilderStore.getState().hydrateFromYaml(BASE_YAML);
  const appended = `${useBuilderStore.getState().yamlDraft}\n# note\n`;
  useBuilderStore.getState().setYamlDraft(appended);
  assert.equal(useBuilderStore.getState().isDirty, true);

  const applied = useBuilderStore.getState().applyYamlDraft();
  assert.equal(applied, true);
  const state = useBuilderStore.getState();
  assert.equal(state.parseError, null);
  assert.equal(state.yamlDraft, state.yamlCanonical);
});

test("applyYamlDraft reports parse errors without mutating canvas nodes", () => {
  useBuilderStore.getState().reset();
  useBuilderStore.getState().hydrateFromYaml(BASE_YAML);
  const nodeCountBefore = useBuilderStore.getState().nodes.length;
  useBuilderStore.getState().setYamlDraft("turns: [");
  const applied = useBuilderStore.getState().applyYamlDraft();
  assert.equal(applied, false);
  const state = useBuilderStore.getState();
  assert.equal(state.nodes.length, nodeCountBefore);
  assert.ok(state.parseError);
});

test("updateNodeTurn mutates node data and can be undone", () => {
  useBuilderStore.getState().reset();
  useBuilderStore.getState().hydrateFromYaml(BASE_YAML);
  const initial = useBuilderStore.getState().nodes[0];
  assert.ok(initial);
  assert.equal(initial.type, "harnessNode");
  useBuilderStore.getState().updateNodeTurn("t1", {
    ...initial.data.turn,
    id: "t1",
    kind: "bot_listen",
  });
  assert.equal(useBuilderStore.getState().nodes[0]?.data.text, "");
  assert.equal(useBuilderStore.getState().nodes[0]?.type, "botNode");

  useBuilderStore.getState().undo();
  assert.equal(useBuilderStore.getState().nodes[0]?.data.text, "hello");
  assert.equal(useBuilderStore.getState().nodes[0]?.type, "harnessNode");
});

test("markSaved clears dirty state after canvas canonical sync", () => {
  useBuilderStore.getState().reset();
  useBuilderStore.getState().hydrateFromYaml(BASE_YAML);
  const stateBefore = useBuilderStore.getState();
  const yaml = flowToYaml({
    nodes: stateBefore.nodes,
    edges: stateBefore.edges,
    meta: stateBefore.meta,
  });
  useBuilderStore.getState().setCanvasCanonicalYaml(`${yaml}\n# changed`);
  assert.equal(useBuilderStore.getState().isDirty, true);
  useBuilderStore.getState().markSaved();
  assert.equal(useBuilderStore.getState().isDirty, false);
});

test("updateMeta mutates metadata and marks draft dirty", () => {
  useBuilderStore.getState().reset();
  useBuilderStore.getState().hydrateFromYaml(BASE_YAML);

  const nextMeta = {
    ...useBuilderStore.getState().meta,
    name: "Updated Name",
  };
  useBuilderStore.getState().updateMeta(nextMeta);

  const state = useBuilderStore.getState();
  assert.equal(state.meta.name, "Updated Name");
  assert.equal(state.syncSource, "canvas");
  assert.equal(state.isDirty, true);
});
