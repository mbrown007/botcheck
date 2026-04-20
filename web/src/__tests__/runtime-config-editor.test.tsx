import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { useForm } from "react-hook-form";
import { RuntimeConfigEditor } from "@/app/(dashboard)/builder/_components/RuntimeConfigEditor";
import { TooltipProvider } from "@/components/ui/tooltip";
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

test("RuntimeConfigEditor renders a live STT provider selector with Azure capability hints", () => {
  function Harness() {
    const { register, setValue, watch, formState } = useForm<ScenarioMetaFormValues>({
      defaultValues: createDefaultValues({
        stt_provider: "azure",
      }),
    });

    return (
      <TooltipProvider>
        <RuntimeConfigEditor
          register={register}
          setValue={setValue}
          watch={watch}
          errors={formState.errors}
          onFocusField={() => {}}
          speechCapabilities={{
            tts: [],
            stt: [
              {
                id: "deepgram",
                label: "Deepgram",
                enabled: true,
                voice_mode: "freeform_id",
                supports_preview: false,
                supports_cache_warm: false,
                supports_live_synthesis: false,
                supports_live_stream: true,
              },
              {
                id: "azure",
                label: "Azure Speech",
                enabled: true,
                voice_mode: "freeform_id",
                supports_preview: false,
                supports_cache_warm: false,
                supports_live_synthesis: false,
                supports_live_stream: true,
              },
            ],
          }}
        />
      </TooltipProvider>
    );
  }

  const markup = renderToStaticMarkup(<Harness />);

  assert.match(markup, /data-testid="builder-stt-provider-select"/);
  assert.doesNotMatch(markup, /data-testid="builder-stt-provider-select"[^>]*disabled/);
  assert.match(markup, />Deepgram</);
  assert.match(markup, />Azure Speech</);
  assert.match(markup, /data-testid="builder-stt-model-input"/);
  assert.match(markup, /placeholder="azure-default"/);
  assert.match(markup, /integer · &gt;= 1 · default 50/);
  assert.match(markup, /string · default en-US/);
});
