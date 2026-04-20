import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { NamespacePath } from "@/components/scenarios/namespace-path";
import { namespaceSegments, normalizeNamespace, summarizeNamespaces } from "@/lib/namespace-context";

test("normalizeNamespace trims repeated separators and blank values", () => {
  assert.equal(normalizeNamespace(" support / billing / "), "support/billing");
  assert.equal(normalizeNamespace(" / / "), null);
  assert.equal(normalizeNamespace(null), null);
});

test("namespaceSegments returns cleaned namespace parts", () => {
  assert.deepEqual(namespaceSegments("support / billing"), ["support", "billing"]);
  assert.deepEqual(namespaceSegments(""), []);
});

test("summarizeNamespaces counts distinct scoped namespaces and unscoped rows", () => {
  assert.deepEqual(
    summarizeNamespaces(["support/billing", "support/billing", "support/refunds", null, ""]),
    { distinctScopedNamespaces: 2, unscopedCount: 2 },
  );
});

test("NamespacePath renders scoped namespace breadcrumbs and unscoped fallback", () => {
  const scopedMarkup = renderToStaticMarkup(
    <NamespacePath namespace="support/billing" compact />
  );
  const unscopedMarkup = renderToStaticMarkup(<NamespacePath namespace={null} compact />);

  assert.match(scopedMarkup, /support/);
  assert.match(scopedMarkup, /billing/);
  assert.match(scopedMarkup, /\//);
  assert.match(unscopedMarkup, /Unscoped/);
});
