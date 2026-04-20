# Developer Guide: Extending the Scenario Builder

This guide explains how the Visual Flow Builder is architected and how to add new logic blocks or extend existing ones.

---

## 1. Architecture Overview

The builder is built using **React Flow** and utilizes a **Single Source of Truth (YAML)** pattern.

### Key Components:
*   **`flow-translator.ts`:** Handles the bidirectional conversion between Scenario YAML and React Flow's `nodes` and `edges` JSON.
*   **`node-registry.ts`:** A central registry that maps block types (e.g., `sayNode`) to their React components and YAML serialization logic.
*   **`useBuilderStore` (Zustand):** Manages the global state of the canvas, the YAML draft, and the dirty state.

---

## 2. Adding a New Logic Block

To add a new type of block (e.g., a "Send SMS" block), follow these steps:

### Step 1: Define the Node Component
Create a new React component in `web/src/components/builder/nodes/`. This component must accept `NodeProps` from React Flow.

```tsx
// Example: CustomNode.tsx
import { Handle, Position, NodeProps } from '@xyflow/react';

export function CustomNode({ data }: NodeProps) {
  return (
    <div className="custom-node-styles">
      <Handle type="target" position={Position.Top} />
      <div>{data.label}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
```

### Step 2: Register the Node Type
Add your new node to the registry in `web/src/lib/node-registry.ts`. You must provide:
1.  **`type`:** The unique string identifier.
2.  **`toYaml`:** A function that converts the node's `data` into a partial YAML `Turn` object.
3.  **`fromYaml`:** A function that extracts node `data` from a YAML `Turn`.

```ts
registerNodeType({
  type: "customNode",
  label: "Custom Action",
  component: CustomNode,
  paletteColor: "bg-purple-500",
  toYaml: (data) => ({ type: "custom", custom_field: data.value }),
  fromYaml: (turn) => ({ value: turn.custom_field }),
});
```

### Step 3: Update the Palette
Add the new node type to the **Node Palette** sidebar component so users can drag it onto the canvas.

---

## 3. Extending the Translator

If your new block requires top-level YAML changes (outside of the `turns` list), you must update the `yamlToFlow` and `flowToYaml` functions in `flow-translator.ts`.

*   **`yamlToFlow`:** Ensure any new top-level keys are captured in the `meta` object.
*   **`flowToYaml`:** Ensure those keys are re-serialized in the correct canonical order.

---

## 4. Testing Parity

Every change to the builder must maintain **Round-trip Parity**. 
1.  Open an existing complex scenario.
2.  Switch to the Builder.
3.  Click Save without making edits.
4.  The resulting YAML should have **zero functional differences** (ignoring minor whitespace/formatting) compared to the original.

Run the parity test suite:
```bash
npm run test:flow-translator
```

---

## 5. Styling Guidelines

The builder uses **Tailwind CSS**.
*   **Nodes:** Should use the `bg-bg-elevated` and `border-border` classes to match the dashboard theme.
*   **Handles:** Use the standard React Flow handles but style them with the node's theme color (e.g., `bg-blue-500` for Say nodes).
*   **Popovers:** Use Radix UI primitives for any inline editing forms within the node.
