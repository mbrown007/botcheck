# Phase 40 AI Voice Results

Use this template after running the live benchmark lanes and generating the
decision matrix.

## Benchmark Metadata

- Date label:
- Environment:
- AI scenario ID:
- Transport profile / destination:
- Tenant:
- Harness worker / metrics target:
- Comparator output:
  - `phase40-ai-voice-decision-matrix.md`
  - `phase40-ai-voice-decision-matrix.json`

## Lane Configuration

### Shared Path

- Evidence bundle:
- Flags confirmed disabled:
  - `ai_voice_preview_events_enabled`
  - `ai_voice_speculative_planning_enabled`
  - `ai_voice_fast_ack_enabled`
  - `ai_voice_early_playback_enabled`

### Overlap Enabled

- Evidence bundle:
- Flags confirmed enabled:
  - `ai_voice_preview_events_enabled`
  - `ai_voice_speculative_planning_enabled`
  - `ai_voice_fast_ack_enabled`
  - `ai_voice_early_playback_enabled`

### Native Speech

- Evidence bundle:
- Phase 39 runtime/provider notes:

## Observed Results

| Lane | Reply avg ms | Decision avg ms | LLM start gap avg ms | Playback gap avg ms | Fast-ack total | Early committed | Early stale | Run errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| shared_path |  |  |  |  |  |  |  |  |
| overlap_enabled |  |  |  |  |  |  |  |  |
| native_speech |  |  |  |  |  |  |  |  |

## Interpretation

### Latency

- Fastest reply lane:
- Lowest decision-to-playback lane:
- Notes:

### Transcript Fidelity

- Shared path:
- Overlap enabled:
- Native speech:

### Debugging Quality

- Shared path:
- Overlap enabled:
- Native speech:

### Provider Flexibility

- Shared path:
- Overlap enabled:
- Native speech:

### Operational Complexity

- Shared path:
- Overlap enabled:
- Native speech:

## Recommendation

- Recommended default lane:
- Recommended fallback lane:
- Keep overlap enabled by default?:
- Keep native speech as opt-in or promote further?:

## Follow-Ups

1.
2.
3.
