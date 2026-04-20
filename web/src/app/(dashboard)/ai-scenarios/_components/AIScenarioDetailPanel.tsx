"use client";

import React from "react";
import type { AIScenarioDetail, SpeechCapabilities } from "@/lib/api/types";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import {
  deriveSttAuthoringState,
  deriveTtsAuthoringState,
  getDefaultModelForSttProvider,
  OPENAI_TTS_VOICE_OPTIONS,
} from "@/lib/speech-authoring";

interface AIScenarioDetailPanelProps {
  scenario: AIScenarioDetail;
  speechCapabilities?: SpeechCapabilities;
  personaName: string;
  onClose: () => void;
}

function formatFacts(facts: Record<string, unknown>): string {
  if (Object.keys(facts).length === 0) {
    return "No structured facts provided.";
  }
  return JSON.stringify(facts, null, 2);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function formatTtsVoiceDetail(
  rawTtsVoice: string,
  speechCapabilities?: SpeechCapabilities
): { label: string; detail: string } {
  const ttsState = deriveTtsAuthoringState(rawTtsVoice, speechCapabilities);
  if (ttsState.parsed.isEmpty) {
    return {
      label: "Platform default",
      detail: "No explicit text-to-speech override is stored.",
    };
  }

  const providerLabel =
    ttsState.allProviders.find((capability) => capability.id === ttsState.parsed.providerId)?.label ??
    ttsState.parsed.providerId;
  const knownVoiceLabel =
    ttsState.parsed.providerId === "openai"
      ? OPENAI_TTS_VOICE_OPTIONS.find((voice) => voice.id === ttsState.parsed.voice)?.label
      : null;

  if (ttsState.currentProviderUnavailable) {
    return {
      label: `${providerLabel} (unavailable)`,
      detail: ttsState.parsed.canonical || ttsState.parsed.raw,
    };
  }

  return {
    label: providerLabel,
    detail:
      knownVoiceLabel ?? (ttsState.parsed.voice || ttsState.parsed.canonical),
  };
}

function formatSttDetail(
  rawSttProvider: string,
  rawSttModel: string,
  speechCapabilities?: SpeechCapabilities
): { label: string; detail: string } {
  const sttState = deriveSttAuthoringState(rawSttProvider, rawSttModel, speechCapabilities);
  const providerId = rawSttProvider.trim().toLowerCase() || sttState.displayProviderId;
  const providerLabel =
    sttState.allProviders.find((capability) => capability.id === providerId)?.label ?? providerId;

  if (!providerId && !rawSttModel.trim()) {
    return {
      label: "Platform default",
      detail: "No explicit speech-to-text override is stored.",
    };
  }

  if (sttState.currentProviderUnavailable) {
    return {
      label: `${providerLabel} (unavailable)`,
      detail: rawSttModel.trim() || "Stored model unavailable",
    };
  }

  return {
    label: providerLabel,
    detail:
      rawSttModel.trim() ||
      sttState.displayModel ||
      getDefaultModelForSttProvider(providerId),
  };
}

export function AIScenarioDetailPanel({
  scenario,
  speechCapabilities,
  personaName,
  onClose,
}: AIScenarioDetailPanelProps) {
  const config = isRecord(scenario.config) ? scenario.config : {};
  const ttsVoice = typeof config.tts_voice === "string" ? config.tts_voice : "";
  const sttProvider = typeof config.stt_provider === "string" ? config.stt_provider : "";
  const sttModel = typeof config.stt_model === "string" ? config.stt_model : "";
  const ttsVoiceDetail = formatTtsVoiceDetail(ttsVoice, speechCapabilities);
  const sttDetail = formatSttDetail(sttProvider, sttModel, speechCapabilities);

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-text-secondary">Scenario Detail</p>
          <h2 className="mt-1 text-lg font-semibold text-text-primary">{scenario.name}</h2>
          {scenario.namespace ? (
            <p className="mt-1 text-[11px] uppercase tracking-[0.18em] text-text-muted">
              {scenario.namespace}
            </p>
          ) : null}
          <p className="mt-1 font-mono text-xs text-text-muted">{scenario.ai_scenario_id}</p>
        </div>
        <Button variant="secondary" size="sm" onClick={onClose}>
          Close
        </Button>
      </CardHeader>
      <CardBody className="space-y-5">
        <div className="grid gap-4 md:grid-cols-5">
          <div>
            <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">Persona</p>
            <p className="mt-1 text-sm text-text-primary">{personaName}</p>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">Namespace</p>
            <p className="mt-1 text-sm text-text-primary">{scenario.namespace || "Unscoped"}</p>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">Opening</p>
            <p className="mt-1 text-sm text-text-primary">
              {scenario.opening_strategy === "wait_for_bot_greeting" ? "Wait for bot" : "Caller opens"}
            </p>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">Records</p>
            <p className="mt-1 text-sm text-text-primary">{scenario.record_count}</p>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">Status</p>
            <div className="mt-1">
              <StatusBadge
                value={scenario.is_active ? "pass" : "pending"}
                label={scenario.is_active ? "active" : "inactive"}
              />
            </div>
          </div>
        </div>

        <div>
          <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">Scenario Brief</p>
          <p className="mt-2 whitespace-pre-wrap rounded-xl border border-border bg-bg-base/60 px-4 py-3 text-sm text-text-secondary">
            {scenario.scenario_brief || "No brief provided."}
          </p>
        </div>

        <div>
          <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">Evaluation Objective</p>
          <p className="mt-2 whitespace-pre-wrap rounded-xl border border-border bg-bg-base/60 px-4 py-3 text-sm text-text-secondary">
            {scenario.evaluation_objective || "No evaluation objective provided."}
          </p>
        </div>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_220px]">
          <div>
            <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">Structured Facts</p>
            <pre className="mt-2 overflow-x-auto rounded-xl border border-border bg-bg-base/60 px-4 py-3 text-xs text-text-secondary">
              {formatFacts(scenario.scenario_facts)}
            </pre>
          </div>
          <div className="space-y-4">
            <div>
              <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">Dataset Source</p>
              <p className="mt-1 text-sm text-text-primary">{scenario.dataset_source || "—"}</p>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">Scoring Profile</p>
              <p className="mt-1 text-sm text-text-primary">{scenario.scoring_profile || "—"}</p>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">TTS Voice</p>
              <p className="mt-1 text-sm text-text-primary">{ttsVoiceDetail.label}</p>
              <p className="mt-1 text-xs text-text-muted">{ttsVoiceDetail.detail}</p>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-[0.18em] text-text-muted">
                STT Provider
              </p>
              <p className="mt-1 text-sm text-text-primary">{sttDetail.label}</p>
              <p className="mt-1 text-xs text-text-muted">{sttDetail.detail}</p>
            </div>
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
