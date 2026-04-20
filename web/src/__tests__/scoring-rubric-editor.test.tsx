import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { useForm } from "react-hook-form";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ScoringRubricEditor } from "@/app/(dashboard)/builder/_components/ScoringRubricEditor";
import type { ScenarioMetaFormValues } from "@/lib/schemas/scenario-meta";

function createDefaultValues(
  overrides: Partial<ScenarioMetaFormValues> = {}
): ScenarioMetaFormValues {
  return {
    id: "scenario-id",
    name: "Scenario",
    namespace: "",
    type: "reliability",
    description: "",
    version: "1.0",
    tags_csv: "",
    max_total_turns: "",
    turn_timeout_s: "",
    max_duration_s: "",
    bot_join_timeout_s: "",
    transfer_timeout_s: "",
    initial_drain_s: "",
    inter_turn_pause_s: "",
    transcript_merge_window_s: "",
    pause_threshold_ms: "",
    stt_endpointing_ms: "",
    language: "",
    stt_provider: "",
    stt_model: "",
    tts_voice: "",
    bot_endpoint: "",
    bot_protocol: "sip",
    bot_trunk_id: "",
    bot_caller_id: "",
    bot_headers_text: "",
    persona_mood: "neutral",
    persona_response_style: "casual",
    timing_gate_p95_response_gap_ms: "",
    timing_warn_p95_response_gap_ms: "",
    timing_gate_interruptions_count: "",
    timing_warn_interruptions_count: "",
    timing_gate_long_pause_count: "",
    timing_warn_long_pause_count: "",
    timing_gate_interruption_recovery_pct: "",
    timing_warn_interruption_recovery_pct: "",
    timing_gate_turn_taking_efficiency_pct: "",
    timing_warn_turn_taking_efficiency_pct: "",
    scoring_overall_gate: true,
    scoring_rubric: [],
    ...overrides,
  };
}

test("ScoringRubricEditor renders custom guidance textarea for each rubric row", () => {
  function Harness() {
    const { control, register, formState } = useForm<ScenarioMetaFormValues>({
      defaultValues: createDefaultValues({
        scoring_rubric: [
          {
            dimension: "policy",
            threshold: 0.8,
            weight: 1,
            gate: true,
            custom_prompt: "Treat unauthorized disclosures as hard failures.",
          },
        ],
      }),
    });

    return (
      <TooltipProvider>
        <ScoringRubricEditor
          control={control}
          register={register}
          errors={formState.errors}
          onFocusField={() => {}}
        />
      </TooltipProvider>
    );
  }

  const markup = renderToStaticMarkup(<Harness />);

  assert.match(markup, /Custom Guidance/);
  assert.match(markup, /data-testid="rubric-custom-prompt-0"/);
  assert.match(markup, /placeholder="Optional dimension-specific judging guidance"/);
});
