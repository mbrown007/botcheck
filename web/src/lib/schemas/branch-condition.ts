import { z } from "zod";
import { isDefaultDecisionSlot } from "@/lib/decision-slots";

export const RESERVED_DEFAULT_CONDITION_MESSAGE =
  "Condition label 'default' is reserved for fallback routing.";
export const EMPTY_CONDITION_MESSAGE = "Condition label cannot be empty.";

export const connectionConditionFormSchema = z.object({
  condition: z.string().refine((value) => {
    const trimmed = value.trim();
    if (!trimmed) {
      return true;
    }
    return !isDefaultDecisionSlot(trimmed);
  }, RESERVED_DEFAULT_CONDITION_MESSAGE),
});

export type ConnectionConditionFormValues = z.infer<
  typeof connectionConditionFormSchema
>;

export const edgeConditionEditFormSchema = z.object({
  condition: z
    .string()
    .trim()
    .min(1, EMPTY_CONDITION_MESSAGE)
    .refine(
      (value) => !isDefaultDecisionSlot(value),
      RESERVED_DEFAULT_CONDITION_MESSAGE
    ),
});

export type EdgeConditionEditFormValues = z.infer<
  typeof edgeConditionEditFormSchema
>;
