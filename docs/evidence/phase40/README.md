# Phase 40 Evidence

Store live-lane benchmark artifacts for the current voice pipeline here.

Recommended layout:

1. One directory per benchmark lane run, for example:
   - `20260321-shared-path/`
   - `20260321-overlap-enabled/`
   - `20260321-native-speech/`
2. Each lane directory should contain the output from
   [`ai_voice_latency_probe.sh`](/scripts/ci/ai_voice_latency_probe.sh):
   - `agent_metrics_before.prom`
   - `agent_metrics_after.prom`
   - `run_details.jsonl`
   - `ai_voice_latency_summary.json`
3. A comparison artifact generated from two or more lane bundles:
   - `phase40-ai-voice-decision-matrix.md`
   - optional `phase40-ai-voice-decision-matrix.json`
4. A filled-in reporting artifact:
   - `phase40-ai-voice-results.md`

The comparison artifact is produced by
[`ai_voice_latency_compare.sh`](/scripts/ci/ai_voice_latency_compare.sh).

To scaffold one benchmark session, use
[`ai_voice_latency_benchmark_plan.sh`](/scripts/ci/ai_voice_latency_benchmark_plan.sh).

For the final written recommendation, start from
[`phase40-ai-voice-results-template.md`](/docs/evidence/phase40/phase40-ai-voice-results-template.md).
