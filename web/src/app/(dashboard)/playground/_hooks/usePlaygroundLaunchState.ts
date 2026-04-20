"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  createPlaygroundPreset,
  createPlaygroundRun,
  deletePlaygroundPreset,
  extractPlaygroundTools,
  generatePlaygroundStubs,
  getAIPersona,
  getPlaygroundPreset,
  patchPlaygroundPreset,
  type PlaygroundExtractedTool,
} from "@/lib/api";
import { mapApiError } from "@/lib/api/error-mapper";
import type {
  AIScenarioSummary,
  BotDestinationSummary,
  PlaygroundPresetSummary,
  ScenarioDefinition,
} from "@/lib/api/types";
import { type PlaygroundMode } from "@/lib/playground";
import {
  buildPlaygroundPresetPatchPayload,
  buildPlaygroundPresetPayload,
  hydratePlaygroundPreset,
  nextPlaygroundPresetCopyName,
} from "@/lib/playground-presets";
import { type TargetChoice } from "../_components/playground-types";

type SearchParamsView = {
  get(name: string): string | null;
  toString(): string;
};

type UsePlaygroundLaunchStateArgs = {
  pathname: string;
  searchParams: SearchParamsView;
  graphScenarios?: ScenarioDefinition[];
  aiScenarios?: AIScenarioSummary[];
  transportProfiles?: BotDestinationSummary[];
  presets?: PlaygroundPresetSummary[];
  mutatePresets: () => Promise<PlaygroundPresetSummary[] | undefined>;
};

type PlaygroundPresetHydration = {
  key: string | null;
  tools: PlaygroundExtractedTool[];
  json: Record<string, string>;
};

export function usePlaygroundLaunchState({
  pathname,
  searchParams,
  graphScenarios,
  aiScenarios,
  transportProfiles,
  presets,
  mutatePresets,
}: UsePlaygroundLaunchStateArgs) {
  const [mode, setMode] = useState<PlaygroundMode>("mock");
  const [targetChoice, setTargetChoice] = useState<TargetChoice>(null);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [personaId, setPersonaId] = useState("");
  const [transportProfileId, setTransportProfileId] = useState("");
  const [selectedPresetId, setSelectedPresetId] = useState("");
  const [presetName, setPresetName] = useState("");
  const [presetDescription, setPresetDescription] = useState("");
  const [runId, setRunId] = useState<string | null>(() => searchParams.get("run_id"));
  const [submitting, setSubmitting] = useState(false);
  const [savingPreset, setSavingPreset] = useState(false);
  const [savingPresetAction, setSavingPresetAction] = useState<
    "create" | "update" | "duplicate" | null
  >(null);
  const [loadingPreset, setLoadingPreset] = useState(false);
  const [deletingPreset, setDeletingPreset] = useState(false);
  const [presetLoaded, setPresetLoaded] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loadingPersonaPrompt, setLoadingPersonaPrompt] = useState(false);
  const [extractedTools, setExtractedTools] = useState<PlaygroundExtractedTool[]>([]);
  const [stubEditorJson, setStubEditorJson] = useState<Record<string, string>>({});
  const [extractingTools, setExtractingTools] = useState(false);
  const [generatingStubs, setGeneratingStubs] = useState(false);
  const [stubError, setStubError] = useState("");
  const presetHydrationRef = useRef<PlaygroundPresetHydration | null>(null);

  const httpTransportProfiles = useMemo(
    () =>
      (transportProfiles ?? []).filter(
        (profile) => profile.protocol === "http" && profile.is_active,
      ),
    [transportProfiles],
  );
  const selectedTransport = useMemo(
    () =>
      httpTransportProfiles.find(
        (profile) => profile.destination_id === transportProfileId,
      ) ?? null,
    [httpTransportProfiles, transportProfileId],
  );
  const selectedPresetSummary = useMemo(
    () => presets?.find((preset) => preset.preset_id === selectedPresetId) ?? null,
    [presets, selectedPresetId],
  );
  const selectedGraphScenario = useMemo(
    () => graphScenarios?.find((scenario) => scenario.id === targetChoice?.id) ?? null,
    [graphScenarios, targetChoice],
  );
  const selectedAIScenario = useMemo(
    () =>
      aiScenarios?.find((scenario) => scenario.ai_scenario_id === targetChoice?.id) ??
      null,
    [aiScenarios, targetChoice],
  );

  const stubSessionKey = targetChoice ? `playground-stubs-${targetChoice.id}` : null;

  const parsedStubs = useMemo(() => {
    const result: Record<string, Record<string, unknown>> = {};
    for (const [name, raw] of Object.entries(stubEditorJson)) {
      try {
        const parsed = JSON.parse(raw) as unknown;
        if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
          result[name] = parsed as Record<string, unknown>;
        }
      } catch {
        // keep undefined — will be detected as invalid below
      }
    }
    return result;
  }, [stubEditorJson]);

  const invalidStubNames = useMemo(
    () => extractedTools.filter((tool) => !(tool.name in parsedStubs)).map((tool) => tool.name),
    [extractedTools, parsedStubs],
  );
  const hasInvalidStubs = invalidStubNames.length > 0 && extractedTools.length > 0;
  const canPersistPreset =
    !!targetChoice &&
    presetName.trim().length > 0 &&
    !hasInvalidStubs &&
    ((mode === "mock" && systemPrompt.trim().length > 0) ||
      (mode === "direct_http" && transportProfileId.length > 0));

  useEffect(() => {
    if (targetChoice) {
      return;
    }
    if (graphScenarios && graphScenarios.length > 0) {
      setTargetChoice({ kind: "graph", id: graphScenarios[0].id });
      return;
    }
    if (aiScenarios && aiScenarios.length > 0) {
      setTargetChoice({ kind: "ai", id: aiScenarios[0].ai_scenario_id });
    }
  }, [aiScenarios, graphScenarios, targetChoice]);

  useEffect(() => {
    const params = new URLSearchParams(searchParams.toString());
    if (runId) {
      params.set("run_id", runId);
    } else {
      params.delete("run_id");
    }
    const next = params.toString() ? `${pathname}?${params.toString()}` : pathname;
    const current = searchParams.toString()
      ? `${pathname}?${searchParams.toString()}`
      : pathname;
    if (next !== current) {
      window.history.replaceState(null, "", next);
    }
  }, [pathname, runId, searchParams]);

  useEffect(() => {
    if (!stubSessionKey) {
      setExtractedTools([]);
      setStubEditorJson({});
      return;
    }
    const pendingHydration = presetHydrationRef.current;
    if (pendingHydration && pendingHydration.key === stubSessionKey) {
      presetHydrationRef.current = null;
      setExtractedTools(pendingHydration.tools);
      setStubEditorJson(pendingHydration.json);
      return;
    }
    try {
      const saved = sessionStorage.getItem(stubSessionKey);
      if (saved) {
        const { tools, json } = JSON.parse(saved) as {
          tools: PlaygroundExtractedTool[];
          json: Record<string, string>;
        };
        setExtractedTools(tools ?? []);
        setStubEditorJson(json ?? {});
        return;
      }
    } catch {
      // ignore corrupt sessionStorage
    }
    setExtractedTools([]);
    setStubEditorJson({});
  }, [stubSessionKey]);

  useEffect(() => {
    if (!stubSessionKey || extractedTools.length === 0) {
      return;
    }
    try {
      sessionStorage.setItem(
        stubSessionKey,
        JSON.stringify({ tools: extractedTools, json: stubEditorJson }),
      );
    } catch {
      // sessionStorage quota exceeded — ignore
    }
  }, [stubSessionKey, extractedTools, stubEditorJson]);

  const handleSelectPreset = useCallback(
    (nextId: string) => {
      setSelectedPresetId(nextId);
      setPresetLoaded(false);
      const nextPreset = presets?.find((preset) => preset.preset_id === nextId) ?? null;
      setPresetName(nextPreset?.name ?? "");
      setPresetDescription(nextPreset?.description ?? "");
    },
    [presets],
  );

  async function handleExtractTools() {
    if (!systemPrompt.trim() || extractingTools) {
      return;
    }
    setExtractingTools(true);
    setStubError("");
    try {
      const tools = await extractPlaygroundTools(systemPrompt);
      setExtractedTools(tools);
      const initial: Record<string, string> = {};
      for (const tool of tools) {
        initial[tool.name] = stubEditorJson[tool.name] ?? JSON.stringify({}, null, 2);
      }
      setStubEditorJson(initial);
    } catch (err) {
      setStubError(mapApiError(err, "Failed to extract tools").message);
    } finally {
      setExtractingTools(false);
    }
  }

  async function handleGenerateStubs() {
    if (extractedTools.length === 0 || generatingStubs) {
      return;
    }
    setGeneratingStubs(true);
    setStubError("");
    try {
      const scenarioName =
        (targetChoice?.kind === "graph"
          ? selectedGraphScenario?.name
          : selectedAIScenario?.name) ?? "";
      const stubs = await generatePlaygroundStubs(extractedTools, scenarioName);
      const next: Record<string, string> = { ...stubEditorJson };
      for (const [name, values] of Object.entries(stubs)) {
        next[name] = JSON.stringify(values, null, 2);
      }
      setStubEditorJson(next);
    } catch (err) {
      setStubError(mapApiError(err, "Failed to generate stubs").message);
    } finally {
      setGeneratingStubs(false);
    }
  }

  async function handleLoadPersonaPrompt() {
    if (!personaId) {
      return;
    }
    setLoadingPersonaPrompt(true);
    setError("");
    try {
      const detail = await getAIPersona(personaId);
      setSystemPrompt(detail.system_prompt ?? "");
    } catch (err) {
      setError(mapApiError(err, "Failed to load persona prompt").message);
    } finally {
      setLoadingPersonaPrompt(false);
    }
  }

  async function handleLoadPreset() {
    if (!selectedPresetId || loadingPreset) {
      return;
    }
    presetHydrationRef.current = null;
    setLoadingPreset(true);
    setError("");
    setSuccess("");
    try {
      const preset = await getPlaygroundPreset(selectedPresetId);
      const hydrated = hydratePlaygroundPreset(preset);
      presetHydrationRef.current = {
        key: hydrated.targetChoice ? `playground-stubs-${hydrated.targetChoice.id}` : null,
        tools: hydrated.extractedTools,
        json: hydrated.stubEditorJson,
      };
      setExtractedTools(hydrated.extractedTools);
      setStubEditorJson(hydrated.stubEditorJson);
      setTargetChoice(hydrated.targetChoice);
      setMode(hydrated.mode);
      setSystemPrompt(hydrated.systemPrompt);
      setPersonaId("");
      setTransportProfileId(hydrated.transportProfileId);
      setPresetName(preset.name);
      setPresetDescription(preset.description ?? "");
      setPresetLoaded(true);
      setSuccess(`Loaded preset "${preset.name}".`);
    } catch (err) {
      setError(mapApiError(err, "Failed to load playground preset").message);
    } finally {
      setLoadingPreset(false);
    }
  }

  async function handleCreatePreset() {
    if (!canPersistPreset || savingPreset) {
      return;
    }
    setSavingPreset(true);
    setSavingPresetAction("create");
    setError("");
    setSuccess("");
    try {
      const payload = buildPlaygroundPresetPayload({
        name: presetName,
        description: presetDescription,
        targetChoice,
        mode,
        systemPrompt,
        transportProfileId,
        parsedStubs,
      });
      if (!payload) {
        setError("Choose a scenario before saving a preset.");
        return;
      }
      const created = await createPlaygroundPreset(payload);
      setSelectedPresetId(created.preset_id);
      setPresetName(created.name);
      setPresetDescription(created.description ?? "");
      await mutatePresets();
      setSuccess(`Saved preset "${created.name}".`);
    } catch (err) {
      setError(mapApiError(err, "Failed to save playground preset").message);
    } finally {
      setSavingPreset(false);
      setSavingPresetAction(null);
    }
  }

  async function handleUpdatePreset() {
    if (!selectedPresetId || !canPersistPreset || savingPreset) {
      return;
    }
    setSavingPreset(true);
    setSavingPresetAction("update");
    setError("");
    setSuccess("");
    try {
      const payload = buildPlaygroundPresetPatchPayload({
        name: presetName,
        description: presetDescription,
        targetChoice,
        mode,
        systemPrompt,
        transportProfileId,
        parsedStubs,
      });
      if (!payload) {
        setError("Choose a scenario before updating a preset.");
        return;
      }
      const updated = await patchPlaygroundPreset(selectedPresetId, payload);
      setPresetName(updated.name);
      setPresetDescription(updated.description ?? "");
      await mutatePresets();
      setSuccess(`Updated preset "${updated.name}".`);
    } catch (err) {
      setError(mapApiError(err, "Failed to update playground preset").message);
    } finally {
      setSavingPreset(false);
      setSavingPresetAction(null);
    }
  }

  async function handleDuplicatePreset() {
    if (!canPersistPreset || savingPreset || deletingPreset) {
      return;
    }
    setSavingPreset(true);
    setSavingPresetAction("duplicate");
    setError("");
    setSuccess("");
    try {
      const freshPresets = await mutatePresets();
      const duplicateName = nextPlaygroundPresetCopyName(
        presetName,
        (freshPresets ?? presets ?? []).map((preset) => preset.name),
      );
      const payload = buildPlaygroundPresetPayload({
        name: duplicateName,
        description: presetDescription,
        targetChoice,
        mode,
        systemPrompt,
        transportProfileId,
        parsedStubs,
      });
      if (!payload) {
        setError("Choose a scenario before duplicating a preset.");
        return;
      }
      const created = await createPlaygroundPreset(payload);
      setSelectedPresetId(created.preset_id);
      setPresetName(created.name);
      setPresetDescription(created.description ?? "");
      await mutatePresets();
      setSuccess(`Saved copy "${created.name}".`);
    } catch (err) {
      setError(mapApiError(err, "Failed to duplicate playground preset").message);
    } finally {
      setSavingPreset(false);
      setSavingPresetAction(null);
    }
  }

  async function handleDeletePreset() {
    if (!selectedPresetId || deletingPreset) {
      return;
    }
    setDeletingPreset(true);
    setError("");
    setSuccess("");
    try {
      const presetLabel = selectedPresetSummary?.name ?? "preset";
      await deletePlaygroundPreset(selectedPresetId);
      setSelectedPresetId("");
      setPresetLoaded(false);
      setPresetName("");
      setPresetDescription("");
      await mutatePresets();
      setSuccess(`Deleted preset "${presetLabel}".`);
    } catch (err) {
      setError(mapApiError(err, "Failed to delete playground preset").message);
    } finally {
      setDeletingPreset(false);
    }
  }

  async function handleRunPlayground() {
    if (!targetChoice || submitting) {
      return;
    }
    setSubmitting(true);
    setError("");
    setSuccess("");
    try {
      const toolStubs =
        mode === "mock" && Object.keys(parsedStubs).length > 0 ? parsedStubs : undefined;
      const payload =
        targetChoice.kind === "graph"
          ? {
              scenario_id: targetChoice.id,
              playground_mode: mode,
              transport_profile_id:
                mode === "direct_http" ? transportProfileId || undefined : undefined,
              system_prompt: mode === "mock" ? systemPrompt.trim() || undefined : undefined,
              tool_stubs: toolStubs,
            }
          : {
              ai_scenario_id: targetChoice.id,
              playground_mode: mode,
              transport_profile_id:
                mode === "direct_http" ? transportProfileId || undefined : undefined,
              system_prompt: mode === "mock" ? systemPrompt.trim() || undefined : undefined,
              tool_stubs: toolStubs,
            };
      const created = await createPlaygroundRun(payload);
      setRunId(created.run_id);
      setSuccess("Playground run created.");
    } catch (err) {
      setError(mapApiError(err, "Failed to create playground run").message);
    } finally {
      setSubmitting(false);
    }
  }

  function notifySuccess(msg: string) {
    setError("");
    setSuccess(msg);
  }

  return {
    canPersistPreset,
    deletingPreset,
    error,
    extractedTools,
    extractingTools,
    generatingStubs,
    handleCreatePreset,
    handleDeletePreset,
    handleDuplicatePreset,
    handleExtractTools,
    handleGenerateStubs,
    handleLoadPersonaPrompt,
    handleLoadPreset,
    handleRunPlayground,
    handleSelectPreset,
    handleUpdatePreset,
    hasInvalidStubs,
    httpTransportProfiles,
    invalidStubNames,
    loadingPersonaPrompt,
    loadingPreset,
    mode,
    notifySuccess,
    personaId,
    presetDescription,
    presetLoaded,
    presetName,
    runId,
    savingPreset,
    savingPresetAction,
    selectedAIScenario,
    selectedGraphScenario,
    selectedPresetId,
    selectedPresetSummary,
    selectedTransport,
    setMode,
    setPersonaId,
    setPresetDescription,
    setPresetName,
    setStubEditorJson,
    setSystemPrompt,
    setTargetChoice,
    setTransportProfileId,
    stubEditorJson,
    stubError,
    submitting,
    success,
    systemPrompt,
    targetChoice,
    transportProfileId,
  };
}
