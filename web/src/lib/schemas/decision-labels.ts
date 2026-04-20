import { z } from "zod";
import { isDefaultDecisionSlot } from "@/lib/decision-slots";

export const DECISION_LABEL_RESERVED_MESSAGE =
  "Condition label 'default' is reserved for fallback routing.";

const decisionLabelValueSchema = z.string().refine((value) => {
  const normalized = value.trim().toLowerCase();
  if (!normalized) {
    return true;
  }
  return !isDefaultDecisionSlot(normalized);
}, DECISION_LABEL_RESERVED_MESSAGE);

export const decisionLabelsFormSchema = z.object({
  labels: z.record(z.string(), decisionLabelValueSchema),
});

export type DecisionLabelsFormValues = z.infer<typeof decisionLabelsFormSchema>;

export function normalizeDecisionLabelInput(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}
