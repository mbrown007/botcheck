import { z } from "zod";
import {
  getBuilderTurnAudioFile,
  getBuilderTurnDtmf,
  getBuilderTurnKind,
  getBuilderTurnListen,
  getBuilderTurnSilenceS,
  getBuilderTurnSpeaker,
  getBuilderTurnText,
  type BuilderTurn,
} from "@/lib/builder-types";
import {
  optionalNonNegativeIntegerStringSchema,
  optionalIntegerStringSchema,
  optionalNonNegativeNumberStringSchema,
  optionalNumberStringSchema,
  optionalPositiveNumberStringSchema,
} from "@/lib/schemas/numeric-string";

export const turnEditorFormSchema = z.object({
  text: z.string(),
  speaker: z.enum(["harness", "bot"]),
  wait_for_response: z.boolean(),
  dtmf: z.string(),
  silence_s: optionalNonNegativeNumberStringSchema,
  audio_file: z.string(),
  max_visits: optionalIntegerStringSchema,
  timeout_s: optionalNumberStringSchema,
  listen_for_s: optionalPositiveNumberStringSchema,
  min_response_duration_s: optionalPositiveNumberStringSchema,
  retry_on_silence: optionalNonNegativeIntegerStringSchema,
  pre_speak_pause_s: optionalNonNegativeNumberStringSchema,
  post_speak_pause_s: optionalNonNegativeNumberStringSchema,
  pre_listen_wait_s: optionalNonNegativeNumberStringSchema,
});

export type TurnEditorFormValues = z.infer<typeof turnEditorFormSchema>;

function parseOptionalNumber(input: string): number | null {
  const trimmed = input.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return parsed;
}

export function turnToFormValues(turn: BuilderTurn): TurnEditorFormValues {
  return {
    text: getBuilderTurnText(turn),
    speaker: getBuilderTurnSpeaker(turn),
    wait_for_response: getBuilderTurnListen(turn),
    dtmf: getBuilderTurnDtmf(turn) ?? "",
    silence_s:
      typeof getBuilderTurnSilenceS(turn) === "number"
        ? String(getBuilderTurnSilenceS(turn))
        : "",
    audio_file: getBuilderTurnAudioFile(turn) ?? "",
    max_visits: typeof turn.max_visits === "number" ? String(turn.max_visits) : "",
    timeout_s: typeof turn.config?.timeout_s === "number" ? String(turn.config.timeout_s) : "",
    listen_for_s:
      typeof turn.config?.listen_for_s === "number" ? String(turn.config.listen_for_s) : "",
    min_response_duration_s:
      typeof turn.config?.min_response_duration_s === "number"
        ? String(turn.config.min_response_duration_s)
        : "",
    retry_on_silence:
      typeof turn.config?.retry_on_silence === "number"
        ? String(turn.config.retry_on_silence)
        : "",
    pre_speak_pause_s:
      typeof turn.config?.pre_speak_pause_s === "number"
        ? String(turn.config.pre_speak_pause_s)
        : "",
    post_speak_pause_s:
      typeof turn.config?.post_speak_pause_s === "number"
        ? String(turn.config.post_speak_pause_s)
        : "",
    pre_listen_wait_s:
      typeof turn.config?.pre_listen_wait_s === "number"
        ? String(turn.config.pre_listen_wait_s)
        : "",
  };
}

export function mergeFormValuesIntoTurn(
  baseTurn: BuilderTurn,
  turnId: string,
  values: TurnEditorFormValues
): BuilderTurn {
  const currentKind = getBuilderTurnKind(baseTurn);

  const nextTurn: BuilderTurn =
    currentKind === "hangup"
      ? {
          ...baseTurn,
          id: turnId,
          kind: "hangup",
        }
      : values.speaker === "bot"
        ? {
            ...baseTurn,
            id: turnId,
            kind: "bot_listen",
          }
        : {
            ...baseTurn,
            id: turnId,
            kind: "harness_prompt",
            content: {},
            listen: values.wait_for_response,
          };

  delete nextTurn.text;
  delete nextTurn.audio_file;
  delete nextTurn.dtmf;
  delete nextTurn.silence_s;
  delete nextTurn.wait_for_response;
  delete nextTurn.speaker;
  // Stale content from a prior harness_prompt must not survive a kind switch.
  if (nextTurn.kind !== "harness_prompt") {
    delete nextTurn.content;
  }

  const dtmfTrimmed = values.dtmf.trim();
  const nextContent =
    nextTurn.kind === "harness_prompt" ? { ...(nextTurn.content ?? {}) } : undefined;

  const silence = parseOptionalNumber(values.silence_s);
  const audioFileTrimmed = values.audio_file.trim();
  const textTrimmed = values.text.trim();

  if (nextContent) {
    if (textTrimmed) {
      nextContent.text = textTrimmed;
    } else {
      delete nextContent.text;
    }
    if (dtmfTrimmed) {
      nextContent.dtmf = dtmfTrimmed;
    } else {
      delete nextContent.dtmf;
    }
    if (silence === null) {
      delete nextContent.silence_s;
    } else {
      nextContent.silence_s = Math.max(0, silence);
    }
    if (audioFileTrimmed) {
      nextContent.audio_file = audioFileTrimmed;
    } else {
      delete nextContent.audio_file;
    }
    nextTurn.content = nextContent;
  }

  const maxVisits = parseOptionalNumber(values.max_visits);
  if (maxVisits === null) {
    delete nextTurn.max_visits;
  } else {
    nextTurn.max_visits = Math.max(0, Math.floor(maxVisits));
  }

  const timeoutS = parseOptionalNumber(values.timeout_s);
  if (timeoutS === null) {
    if (nextTurn.config) {
      const nextConfig = { ...nextTurn.config };
      delete nextConfig.timeout_s;
      if (Object.keys(nextConfig).length > 0) {
        nextTurn.config = nextConfig;
      } else {
        delete nextTurn.config;
      }
    }
  } else {
    nextTurn.config = {
      ...(nextTurn.config ?? {}),
      timeout_s: Math.max(1, Math.floor(timeoutS)),
    };
  }

  const listenForS = parseOptionalNumber(values.listen_for_s);
  if (listenForS === null) {
    if (nextTurn.config) {
      const nextConfig = { ...nextTurn.config };
      delete nextConfig.listen_for_s;
      if (Object.keys(nextConfig).length > 0) {
        nextTurn.config = nextConfig;
      } else {
        delete nextTurn.config;
      }
    }
  } else {
    nextTurn.config = {
      ...(nextTurn.config ?? {}),
      listen_for_s: Math.max(0.1, listenForS),
    };
  }

  const minResponseDurationS = parseOptionalNumber(values.min_response_duration_s);
  if (minResponseDurationS === null) {
    if (nextTurn.config) {
      const nextConfig = { ...nextTurn.config };
      delete nextConfig.min_response_duration_s;
      if (Object.keys(nextConfig).length > 0) {
        nextTurn.config = nextConfig;
      } else {
        delete nextTurn.config;
      }
    }
  } else {
    nextTurn.config = {
      ...(nextTurn.config ?? {}),
      min_response_duration_s: Math.max(0.1, minResponseDurationS),
    };
  }

  const retryOnSilence = parseOptionalNumber(values.retry_on_silence);
  if (retryOnSilence === null) {
    if (nextTurn.config) {
      const nextConfig = { ...nextTurn.config };
      delete nextConfig.retry_on_silence;
      if (Object.keys(nextConfig).length > 0) {
        nextTurn.config = nextConfig;
      } else {
        delete nextTurn.config;
      }
    }
  } else {
    nextTurn.config = {
      ...(nextTurn.config ?? {}),
      retry_on_silence: Math.max(0, Math.floor(retryOnSilence)),
    };
  }

  const preSpeakPauseS = parseOptionalNumber(values.pre_speak_pause_s);
  if (preSpeakPauseS === null) {
    if (nextTurn.config) {
      const nextConfig = { ...nextTurn.config };
      delete nextConfig.pre_speak_pause_s;
      if (Object.keys(nextConfig).length > 0) {
        nextTurn.config = nextConfig;
      } else {
        delete nextTurn.config;
      }
    }
  } else {
    nextTurn.config = {
      ...(nextTurn.config ?? {}),
      pre_speak_pause_s: Math.max(0, preSpeakPauseS),
    };
  }

  const postSpeakPauseS = parseOptionalNumber(values.post_speak_pause_s);
  if (postSpeakPauseS === null) {
    if (nextTurn.config) {
      const nextConfig = { ...nextTurn.config };
      delete nextConfig.post_speak_pause_s;
      if (Object.keys(nextConfig).length > 0) {
        nextTurn.config = nextConfig;
      } else {
        delete nextTurn.config;
      }
    }
  } else {
    nextTurn.config = {
      ...(nextTurn.config ?? {}),
      post_speak_pause_s: Math.max(0, postSpeakPauseS),
    };
  }

  const preListenWaitS = parseOptionalNumber(values.pre_listen_wait_s);
  if (preListenWaitS === null) {
    if (nextTurn.config) {
      const nextConfig = { ...nextTurn.config };
      delete nextConfig.pre_listen_wait_s;
      if (Object.keys(nextConfig).length > 0) {
        nextTurn.config = nextConfig;
      } else {
        delete nextTurn.config;
      }
    }
  } else {
    nextTurn.config = {
      ...(nextTurn.config ?? {}),
      pre_listen_wait_s: Math.max(0, preListenWaitS),
    };
  }

  return nextTurn;
}
