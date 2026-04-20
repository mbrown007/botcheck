import test from "node:test";
import assert from "node:assert/strict";
import { yamlToFlow } from "../lib/flow-translator";
import {
  computeNodeStructuralErrors,
  describeScenarioValidationErrors,
} from "../lib/builder-validation";

const BASE_YAML = `version: "1.0"
id: builder-validation
name: Builder Validation
type: reliability
description: validation test
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
      text: start
    listen: true
  - id: t2
    kind: harness_prompt
    content:
      text: next
    listen: true
`;

test("computeNodeStructuralErrors returns no errors for simple valid flow", () => {
  const flow = yamlToFlow(BASE_YAML);
  const errors = computeNodeStructuralErrors(flow.nodes, flow.edges);
  assert.deepEqual(errors, {});
});

test("computeNodeStructuralErrors flags harness turns without content", () => {
  const flow = yamlToFlow(BASE_YAML);
  const t1 = flow.nodes.find((node) => node.id === "t1");
  assert.ok(t1);
  t1.data.turn.content = {};
  t1.data.text = "";
  const errors = computeNodeStructuralErrors(flow.nodes, flow.edges);
  assert.ok(errors.t1);
  assert.ok(
    (errors.t1 ?? []).some((message) =>
      message.includes("Harness turn requires text")
    )
  );
});

test("computeNodeStructuralErrors flags multi-exit nodes without default edge", () => {
  const flow = yamlToFlow(BASE_YAML);
  flow.edges = [
    {
      id: "e1",
      source: "t1",
      target: "t2",
      data: { condition: "alpha" },
    },
    {
      id: "e2",
      source: "t1",
      target: "t2",
      data: { condition: "beta" },
    },
  ];
  const errors = computeNodeStructuralErrors(flow.nodes, flow.edges);
  assert.ok(errors.t1);
  assert.ok(
    (errors.t1 ?? []).some((message) =>
      message.includes("require one default edge")
    )
  );
});

test("computeNodeStructuralErrors flags keyword branches without match rules", () => {
  const flow = yamlToFlow(`version: "1.0"
id: keyword-validation
name: Keyword Validation
type: reliability
description: branch rule validation
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
      text: choose
    listen: true
    branching:
      mode: keyword
      cases:
        - condition: billing
          next: t2
      default: t2
  - id: t2
    kind: harness_prompt
    content:
      text: done
    listen: true
`);
  const errors = computeNodeStructuralErrors(flow.nodes, flow.edges);
  assert.ok(
    (errors.t1 ?? []).some((message) =>
      message.includes('Branch "billing" requires a keyword match.')
    )
  );
});

test("computeNodeStructuralErrors flags invalid regex branches", () => {
  const flow = yamlToFlow(`version: "1.0"
id: regex-validation
name: Regex Validation
type: reliability
description: regex validation
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
      text: choose
    listen: true
    branching:
      mode: regex
      cases:
        - condition: billing
          regex: "("
          next: t2
      default: t2
  - id: t2
    kind: harness_prompt
    content:
      text: done
    listen: true
`);
  const errors = computeNodeStructuralErrors(flow.nodes, flow.edges);
  assert.ok(
    (errors.t1 ?? []).some((message) =>
      message.includes('Branch "billing" has an invalid regex.')
    )
  );
});

test("computeNodeStructuralErrors flags invalid time route windows", () => {
  const flow = yamlToFlow(`version: "1.0"
id: time-route-validation
name: Time Route Validation
type: reliability
description: time route validation
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
  - id: t_route
    kind: time_route
    timezone: UTC
    windows:
      - label: business_hours
        start: 09:00
        end: 17:00
        next: t_done
    default: t_done
  - id: t_done
    kind: hangup
`);
  const routeNode = flow.nodes.find((node) => node.id === "t_route");
  assert.ok(routeNode);
  routeNode.data.turn.windows = [
    {
      label: "business_hours",
      start: "nope",
      end: "09:00",
      next: "t_done",
    },
  ];
  const errors = computeNodeStructuralErrors(flow.nodes, flow.edges);
  assert.ok(
    (errors.t_route ?? []).some((message) =>
      message.includes('Time route window "business_hours" requires start in HH:MM format.')
    )
  );
});

test("describeScenarioValidationErrors maps turn-index validation errors to node ids", () => {
  const described = describeScenarioValidationErrors(
    [
      {
        field: "turns.0.windows.0.next",
        message: "Time route window \"business_hours\" must reference an existing turn id.",
      },
      {
        field: "turns.0.default",
        message: "Time route default must reference an existing turn id.",
      },
    ],
    `version: "1.0"
id: time-route-validation-errors
name: Time Route Validation Errors
type: reliability
description: validation mapping
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
  - id: t_route
    kind: time_route
    timezone: UTC
    windows:
      - label: business_hours
        start: 09:00
        end: 17:00
        next: ""
    default: ""
`
  );

  assert.deepEqual(described.nodeErrors.t_route, [
    'Time route window "business_hours" must reference an existing turn id.',
    "Time route default must reference an existing turn id.",
  ]);
  assert.match(described.saveError, /t_route: Time route window "business_hours"/);
  assert.match(described.saveError, /t_route: Time route default must reference an existing turn id\./);
});

test("describeScenarioValidationErrors keeps top-level validation errors in the banner", () => {
  const described = describeScenarioValidationErrors(
    [
      {
        field: "bot.endpoint",
        message: "Field required",
      },
    ],
    BASE_YAML
  );

  assert.deepEqual(described.nodeErrors, {});
  assert.match(described.saveError, /bot\.endpoint: Field required/);
});
