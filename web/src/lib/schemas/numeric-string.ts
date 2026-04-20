import { z } from "zod";

export const optionalNumberStringSchema = z
  .string()
  .trim()
  .refine((value) => value === "" || /^-?\d+(\.\d+)?$/.test(value), {
    message: "Use a number",
  });

export const optionalNonNegativeNumberStringSchema = optionalNumberStringSchema.refine(
  (value) => value === "" || Number(value) >= 0,
  {
    message: "Must be at least 0",
  }
);

export const optionalPositiveNumberStringSchema = optionalNumberStringSchema.refine(
  (value) => value === "" || Number(value) > 0,
  {
    message: "Must be greater than 0",
  }
);

export const optionalIntegerStringSchema = z
  .string()
  .trim()
  .refine((value) => value === "" || /^-?\d+$/.test(value), {
    message: "Use a whole number",
  });

export const optionalNonNegativeIntegerStringSchema = optionalIntegerStringSchema.refine(
  (value) => value === "" || Number(value) >= 0,
  {
    message: "Must be at least 0",
  }
);

export const optionalPositiveIntegerStringSchema = optionalIntegerStringSchema.refine(
  (value) => value === "" || Number(value) >= 1,
  {
    message: "Must be at least 1",
  }
);
