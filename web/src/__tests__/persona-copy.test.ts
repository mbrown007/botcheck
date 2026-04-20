import assert from "node:assert/strict";
import test from "node:test";
import { nextPersonaCopyDisplayName, nextPersonaCopyHandle } from "@/lib/persona-copy";

test("nextPersonaCopyDisplayName creates the first available copy label", () => {
  assert.equal(
    nextPersonaCopyDisplayName("Liam White", ["Liam White", "Someone Else"]),
    "Liam White Copy"
  );
});

test("nextPersonaCopyDisplayName increments when copy labels already exist", () => {
  assert.equal(
    nextPersonaCopyDisplayName("Liam White", [
      "Liam White",
      "Liam White Copy",
      "Liam White Copy 2",
    ]),
    "Liam White Copy 3"
  );
});

test("nextPersonaCopyHandle increments handle copies safely", () => {
  assert.equal(
    nextPersonaCopyHandle("liam_white", ["liam_white", "liam_white_copy", "liam_white_copy_2"]),
    "liam_white_copy_3"
  );
});
