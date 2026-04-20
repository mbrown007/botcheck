import assert from "node:assert/strict";
import test from "node:test";
import {
  optionalIntegerStringSchema,
  optionalNonNegativeIntegerStringSchema,
  optionalNonNegativeNumberStringSchema,
  optionalNumberStringSchema,
  optionalPositiveIntegerStringSchema,
  optionalPositiveNumberStringSchema,
} from "../lib/schemas/numeric-string";

test("optionalNumberStringSchema accepts empty, negatives, and decimals", () => {
  assert.equal(optionalNumberStringSchema.safeParse("").success, true);
  assert.equal(optionalNumberStringSchema.safeParse("-2.5").success, true);
  assert.equal(optionalNumberStringSchema.safeParse("4.2").success, true);
  assert.equal(optionalNumberStringSchema.safeParse("abc").success, false);
});

test("optionalNonNegativeNumberStringSchema rejects negatives", () => {
  assert.equal(optionalNonNegativeNumberStringSchema.safeParse("").success, true);
  assert.equal(optionalNonNegativeNumberStringSchema.safeParse("0").success, true);
  assert.equal(optionalNonNegativeNumberStringSchema.safeParse("1.5").success, true);
  assert.equal(optionalNonNegativeNumberStringSchema.safeParse("-0.1").success, false);
});

test("optionalPositiveNumberStringSchema requires > 0", () => {
  assert.equal(optionalPositiveNumberStringSchema.safeParse("").success, true);
  assert.equal(optionalPositiveNumberStringSchema.safeParse("0.1").success, true);
  assert.equal(optionalPositiveNumberStringSchema.safeParse("0").success, false);
});

test("optionalIntegerStringSchema requires whole numbers", () => {
  assert.equal(optionalIntegerStringSchema.safeParse("").success, true);
  assert.equal(optionalIntegerStringSchema.safeParse("-4").success, true);
  assert.equal(optionalIntegerStringSchema.safeParse("2").success, true);
  assert.equal(optionalIntegerStringSchema.safeParse("1.5").success, false);
});

test("optionalNonNegativeIntegerStringSchema requires whole numbers >= 0", () => {
  assert.equal(optionalNonNegativeIntegerStringSchema.safeParse("").success, true);
  assert.equal(optionalNonNegativeIntegerStringSchema.safeParse("0").success, true);
  assert.equal(optionalNonNegativeIntegerStringSchema.safeParse("7").success, true);
  assert.equal(optionalNonNegativeIntegerStringSchema.safeParse("-1").success, false);
  assert.equal(optionalNonNegativeIntegerStringSchema.safeParse("2.5").success, false);
});

test("optionalPositiveIntegerStringSchema requires >= 1", () => {
  assert.equal(optionalPositiveIntegerStringSchema.safeParse("").success, true);
  assert.equal(optionalPositiveIntegerStringSchema.safeParse("1").success, true);
  assert.equal(optionalPositiveIntegerStringSchema.safeParse("0").success, false);
  assert.equal(optionalPositiveIntegerStringSchema.safeParse("-3").success, false);
});
