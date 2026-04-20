import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { TableState } from "@/components/ui/table-state";

test("TableState renders loading skeleton rows and message", () => {
  const markup = renderToStaticMarkup(
    createElement(TableState, {
      kind: "loading",
      message: "Loading runs...",
      columns: 3,
      rows: 2,
    })
  );

  assert.ok(markup.includes("Loading runs..."));
  assert.equal((markup.match(/animate-pulse/g) ?? []).length, 6);
  assert.ok(markup.includes("animate-spin"));
});

test("TableState renders empty state defaults", () => {
  const markup = renderToStaticMarkup(
    createElement(TableState, {
      kind: "empty",
      message: "No runs have been started yet.",
    })
  );

  assert.ok(markup.includes("Nothing to show"));
  assert.ok(markup.includes("No runs have been started yet."));
});

test("TableState renders error state title and message", () => {
  const markup = renderToStaticMarkup(
    createElement(TableState, {
      kind: "error",
      title: "Runs unavailable",
      message: "The API did not respond.",
    })
  );

  assert.ok(markup.includes("Runs unavailable"));
  assert.ok(markup.includes("The API did not respond."));
  assert.ok(markup.includes("text-fail"));
});
