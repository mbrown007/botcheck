"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useRef } from "react";
import { useForm } from "react-hook-form";
import { useBuilderStore } from "@/lib/builder-store";
import {
  areMetaFormValuesEqual,
  mergeFormValuesIntoMeta,
  metaToFormValues,
  scenarioMetaFormSchema,
  type ScenarioMetaFormValues,
} from "@/lib/schemas/scenario-meta";

const METADATA_SYNC_DEBOUNCE_MS = 160;

export function useMetadataForm() {
  const meta = useBuilderStore((state) => state.meta);
  const updateMeta = useBuilderStore((state) => state.updateMeta);
  const checkpoint = useBuilderStore((state) => state.checkpoint);

  const syncTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const form = useForm<ScenarioMetaFormValues>({
    resolver: zodResolver(scenarioMetaFormSchema),
    mode: "onChange",
    defaultValues: metaToFormValues(meta),
  });

  const { watch, reset, getValues, setValue } = form;

  useEffect(() => {
    const nextValues = metaToFormValues(meta);
    const currentValues = getValues();
    if (areMetaFormValuesEqual(nextValues, currentValues)) {
      return;
    }
    reset(nextValues);
  }, [getValues, meta, reset]);

  useEffect(() => {
    const subscription = watch((candidateValues) => {
      const parsed = scenarioMetaFormSchema.safeParse(candidateValues);
      if (!parsed.success) {
        return;
      }
      if (syncTimerRef.current) {
        clearTimeout(syncTimerRef.current);
      }
      syncTimerRef.current = setTimeout(() => {
        const currentMeta = useBuilderStore.getState().meta;
        const nextMeta = mergeFormValuesIntoMeta(currentMeta, parsed.data);
        const currentFormValues = metaToFormValues(currentMeta);
        const nextFormValues = metaToFormValues(nextMeta);
        if (areMetaFormValuesEqual(currentFormValues, nextFormValues)) {
          return;
        }
        updateMeta(nextMeta);
      }, METADATA_SYNC_DEBOUNCE_MS);
    });
    return () => subscription.unsubscribe();
  }, [updateMeta, watch]);

  useEffect(() => {
    return () => {
      if (syncTimerRef.current) {
        clearTimeout(syncTimerRef.current);
      }
    };
  }, []);

  return {
    form,
    onMetadataFieldFocus: checkpoint,
    watch,
    setValue,
  };
}
