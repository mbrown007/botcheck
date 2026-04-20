"use client";

import { useCallback, useEffect } from "react";
import { flowToYaml } from "@/lib/flow-translator";
import { readLayoutPositions, writeLayoutPositions } from "@/lib/flow-layout-storage";
import { useBuilderStore } from "@/lib/builder-store";

export function useBuilderSync(layoutKey: string) {
  const nodes = useBuilderStore((state) => state.nodes);
  const edges = useBuilderStore((state) => state.edges);
  const meta = useBuilderStore((state) => state.meta);
  const syncSource = useBuilderStore((state) => state.syncSource);
  const setCanvasCanonicalYaml = useBuilderStore((state) => state.setCanvasCanonicalYaml);
  const applyYamlDraft = useBuilderStore((state) => state.applyYamlDraft);
  const checkpoint = useBuilderStore((state) => state.checkpoint);

  // Debounced canvas → YAML sync (300ms)
  useEffect(() => {
    if (syncSource !== "canvas") {
      return;
    }
    const timer = window.setTimeout(() => {
      const yaml = flowToYaml({ nodes, edges, meta });
      setCanvasCanonicalYaml(yaml);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [edges, meta, nodes, setCanvasCanonicalYaml, syncSource]);

  const handleApplyYaml = useCallback(() => {
    checkpoint();
    const savedPositions = readLayoutPositions(layoutKey);
    const ok = applyYamlDraft(savedPositions);
    if (ok) {
      writeLayoutPositions(layoutKey, useBuilderStore.getState().nodes);
    }
  }, [applyYamlDraft, checkpoint, layoutKey]);

  return { handleApplyYaml };
}
