"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  previewSchedule,
  type MisfirePolicy,
  type ScheduleCreateRequest,
  type SchedulePatchRequest,
  type ScheduleResponse,
  useAIScenarios,
  useFeatures,
  usePacks,
  useScenarios,
  useTenant,
  useTransportProfiles,
} from "@/lib/api";
import { describeTransportDispatch } from "@/lib/destination-display";
import {
  COMMON_TIMEZONES,
  FREQUENCY_PRESETS,
  type FrequencyPreset,
  type ScheduleTargetType,
} from "@/components/schedules/schedule-form-helpers";

type Mode = "create" | "edit";

export function useScheduleFormState(options: { mode: Mode; schedule?: ScheduleResponse }) {
  const { mode, schedule } = options;
  const { data: scenarios } = useScenarios();
  const { data: packs } = usePacks();
  const { data: features } = useFeatures();
  const aiEnabled = features?.ai_scenarios_enabled === true;
  const { data: aiScenarios } = useAIScenarios(aiEnabled);
  const destinationsEnabled = features?.destinations_enabled === true;
  const { data: destinations } = useTransportProfiles(destinationsEnabled);
  const { data: tenant } = useTenant();
  const defaultTimezone = tenant?.instance_timezone || "UTC";
  const scheduleOverrides = ((schedule?.config_overrides ?? {}) as Record<string, unknown>) || {};

  const initialTargetType = (schedule?.target_type as ScheduleTargetType | undefined) ?? "scenario";
  const initialName = schedule?.name ?? "";
  const initialScenarioId = schedule?.scenario_id ?? "";
  const initialAiScenarioId = schedule?.ai_scenario_id ?? "";
  const initialPackId = schedule?.pack_id ?? "";
  const initialDestinationId =
    typeof scheduleOverrides.transport_profile_id === "string"
      ? scheduleOverrides.transport_profile_id
      : typeof scheduleOverrides.destination_id === "string"
        ? scheduleOverrides.destination_id
        : "";
  const initialBotEndpoint =
    typeof scheduleOverrides.dial_target === "string"
      ? scheduleOverrides.dial_target
      : typeof scheduleOverrides.bot_endpoint === "string"
        ? scheduleOverrides.bot_endpoint
        : "";
  const initialPreset =
    FREQUENCY_PRESETS.find((row) => row.cron === schedule?.cron_expr)?.value ?? "daily";

  const [targetType, setTargetType] = useState<ScheduleTargetType>(initialTargetType);
  const [name, setName] = useState(initialName);
  const [scenarioId, setScenarioId] = useState(initialScenarioId);
  const [aiScenarioId, setAiScenarioId] = useState(initialAiScenarioId);
  const [packId, setPackId] = useState(initialPackId);
  const [botEndpoint, setBotEndpoint] = useState(initialBotEndpoint);
  const [destinationId, setDestinationId] = useState(initialDestinationId);
  const [preset, setPreset] = useState<FrequencyPreset>(initialPreset);
  const [cronExpr, setCronExpr] = useState(schedule?.cron_expr ?? "0 9 * * *");
  const [timezone, setTimezone] = useState(schedule?.timezone ?? "");
  const [active, setActive] = useState(schedule?.active ?? true);
  const [retryOnFailure, setRetryOnFailure] = useState(schedule?.retry_on_failure ?? false);
  const [misfirePolicy, setMisfirePolicy] = useState<MisfirePolicy>(schedule?.misfire_policy ?? "skip");
  const [previewTz, setPreviewTz] = useState(schedule?.timezone ?? "UTC");
  const [previewTimes, setPreviewTimes] = useState<string[]>([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const previewReq = useRef(0);

  useEffect(() => {
    if (!timezone) {
      setTimezone(defaultTimezone);
    }
  }, [defaultTimezone, timezone]);

  const timezoneOptions = useMemo(() => {
    if (COMMON_TIMEZONES.includes(defaultTimezone)) {
      return COMMON_TIMEZONES;
    }
    return [defaultTimezone, ...COMMON_TIMEZONES];
  }, [defaultTimezone]);

  const graphScenarios = useMemo(
    () => (scenarios ?? []).filter((row) => row.scenario_kind !== "ai"),
    [scenarios],
  );

  const dispatchHint = useMemo(
    () =>
      describeTransportDispatch({
        destinations,
        transportProfileId: destinationId,
        dialTarget: botEndpoint,
        fallbackTargetLabel:
          targetType === "scenario" ? "scenario endpoint" : "child scenario endpoint",
      }),
    [destinations, destinationId, botEndpoint, targetType],
  );

  const onChangePreset = (value: FrequencyPreset) => {
    setPreset(value);
    const presetDef = FREQUENCY_PRESETS.find((item) => item.value === value);
    if (presetDef) {
      setCronExpr(presetDef.cron);
    }
  };

  useEffect(() => {
    if (!cronExpr.trim()) {
      setPreviewTimes([]);
      setPreviewError("");
      setPreviewTz(timezone || defaultTimezone);
      return;
    }
    const handle = setTimeout(() => {
      const reqId = ++previewReq.current;
      setPreviewLoading(true);
      setPreviewError("");
      void previewSchedule(cronExpr, timezone || undefined, 5)
        .then((result) => {
          if (previewReq.current !== reqId) return;
          setPreviewTz(result.timezone);
          setPreviewTimes(result.occurrences);
        })
        .catch((err) => {
          if (previewReq.current !== reqId) return;
          setPreviewTimes([]);
          setPreviewError(err instanceof Error ? err.message : "Preview failed");
        })
        .finally(() => {
          if (previewReq.current === reqId) setPreviewLoading(false);
        });
    }, 350);
    return () => clearTimeout(handle);
  }, [cronExpr, timezone, defaultTimezone]);

  const canSubmit =
    !submitting &&
    !previewLoading &&
    (targetType === "scenario" ? Boolean(scenarioId || aiScenarioId) : Boolean(packId)) &&
    Boolean(cronExpr) &&
    Boolean(timezone);

  const validate = () => {
    if (targetType === "scenario" && !scenarioId && !aiScenarioId) {
      return "Graph scenario or AI scenario is required";
    }
    if (targetType === "pack" && !packId) {
      return "Pack is required";
    }
    return "";
  };

  const buildPayload = (): ScheduleCreateRequest | SchedulePatchRequest => {
    const normalizedName = name.trim();
    const base = {
      name: normalizedName || null,
      target_type: targetType,
      scenario_id: targetType === "scenario" ? scenarioId || null : null,
      ai_scenario_id: targetType === "scenario" ? aiScenarioId || null : null,
      pack_id: targetType === "pack" ? packId || null : null,
      cron_expr: cronExpr,
      timezone,
      active,
      retry_on_failure: targetType === "scenario" ? retryOnFailure : false,
      misfire_policy: misfirePolicy,
    };

    if (mode === "create") {
      const configOverrides: Record<string, unknown> = {};
      if (botEndpoint.trim()) {
        configOverrides.dial_target = botEndpoint.trim();
      }
      if (destinationId) {
        configOverrides.transport_profile_id = destinationId;
      }
      return {
        ...base,
        config_overrides: Object.keys(configOverrides).length > 0 ? configOverrides : undefined,
      };
    }

    const patchBody: SchedulePatchRequest = { ...base };
    if (destinationId !== initialDestinationId || botEndpoint !== initialBotEndpoint) {
      const nextOverrides = { ...scheduleOverrides };
      delete nextOverrides.transport_profile_id;
      delete nextOverrides.destination_id;
      delete nextOverrides.dial_target;
      delete nextOverrides.bot_endpoint;
      if (destinationId) {
        nextOverrides.transport_profile_id = destinationId;
      }
      if (botEndpoint.trim()) {
        nextOverrides.dial_target = botEndpoint.trim();
      }
      patchBody.config_overrides = nextOverrides;
    }
    return patchBody;
  };

  return {
    aiEnabled,
    aiScenarios,
    aiScenarioId,
    active,
    botEndpoint,
    canSubmit,
    cronExpr,
    defaultTimezone,
    destinations,
    destinationsEnabled,
    destinationId,
    dispatchHint,
    error,
    graphScenarios,
    misfirePolicy,
    name,
    onChangePreset,
    packId,
    packs,
    preset,
    previewError,
    previewLoading,
    previewTimes,
    previewTz,
    retryOnFailure,
    scenarioId,
    setActive,
    setAiScenarioId,
    setBotEndpoint,
    setCronExpr,
    setDestinationId,
    setError,
    setMisfirePolicy,
    setName,
    setPackId,
    setRetryOnFailure,
    setScenarioId,
    setSubmitting,
    setTargetType,
    setTimezone,
    submitting,
    targetType,
    timezone,
    timezoneOptions,
    validate,
    buildPayload,
  };
}
