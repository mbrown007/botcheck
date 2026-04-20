/**
 * API type parity assertions.
 *
 * Each assertion here is a compile-time check: if a type exported from a
 * module diverges from its generated counterpart, tsc --noEmit fails and the
 * test suite exits non-zero.
 *
 * Add an entry here whenever you expose a generated schema type through a
 * wrapper module (types.ts, playground.ts, etc.) so that drift is caught
 * before it reaches a PR.
 *
 * The pattern:
 *   type _Assert = Exact<LocalType, GeneratedType>;
 *   const _: _Assert = true;   // fails to compile if types diverge
 */

import type { components } from "@/lib/api/generated";
import type { PlaygroundExtractedTool } from "@/lib/api/playground";

type Generated = components["schemas"];

// Bidirectional assignability — catches added, removed, or changed fields.
type Exact<A, B> = A extends B ? (B extends A ? true : never) : never;

// ---------------------------------------------------------------------------
// Playground types
// ---------------------------------------------------------------------------

type _PlaygroundExtractedToolParity = Exact<
  PlaygroundExtractedTool,
  Generated["PlaygroundExtractedTool"]
>;
const _playgroundExtractedTool: _PlaygroundExtractedToolParity = true;

// Silence unused-variable warnings without affecting the compile-time check.
void _playgroundExtractedTool;

// ---------------------------------------------------------------------------
// Runtime check (node:test doesn't run this file as tests unless there is
// at least one test block, so we add a trivial one).
// ---------------------------------------------------------------------------
import { describe, it } from "node:test";
import assert from "node:assert/strict";

describe("api-type-parity", () => {
  it("compile-time assertions passed (file compiled successfully)", () => {
    assert.ok(true);
  });
});
