import type { BuilderState, BuilderStoreGet, BuilderStoreSet } from "./types";
import { flowToYaml, yamlToFlow } from "@/lib/flow-translator";
import { baseSnapshot, createSnapshot } from "./snapshot";
import { withHistoryPush } from "./history-utils";

type IoSlice = Pick<
  BuilderState,
  | "parseError"
  | "statusMessage"
  | "setStatusMessage"
  | "setYamlDraft"
  | "hydrateFromYaml"
  | "applyYamlDraft"
  | "setCanvasCanonicalYaml"
  | "markSaved"
  | "reset"
>;

export function createIoSlice(set: BuilderStoreSet, get: BuilderStoreGet): IoSlice {
  return {
    parseError: null,
    statusMessage: null,

    setStatusMessage: (message) => {
      set({ statusMessage: message });
    },

    setYamlDraft: (yaml) => {
      set((state) => ({
        yamlDraft: yaml,
        syncSource: "yaml",
        statusMessage: null,
        parseError: null,
        isDirty: yaml !== state.persistedYaml,
      }));
    },

    hydrateFromYaml: (yaml, savedPositions) => {
      const flowDoc = yamlToFlow(yaml, savedPositions);
      const canonical = flowToYaml(flowDoc);
      set({
        nodes: flowDoc.nodes,
        edges: flowDoc.edges,
        meta: flowDoc.meta,
        yamlCanonical: canonical,
        yamlDraft: canonical,
        persistedYaml: canonical,
        isDirty: false,
        syncSource: "yaml",
        parseError: null,
        statusMessage: null,
        historyPast: [],
        historyFuture: [],
        canUndo: false,
        canRedo: false,
      });
    },

    applyYamlDraft: (savedPositions) => {
      try {
        const state = get();
        const flowDoc = yamlToFlow(state.yamlDraft, savedPositions);
        const canonical = flowToYaml(flowDoc);
        if (canonical === state.yamlCanonical) {
          set((currentState) => ({
            yamlDraft: canonical,
            syncSource: "yaml",
            parseError: null,
            statusMessage: "YAML already in sync",
            isDirty: canonical !== currentState.persistedYaml,
          }));
          return true;
        }
        set((currentState) => {
          const snapshot = createSnapshot(currentState);
          const historyState = withHistoryPush(currentState, snapshot);
          return {
            nodes: flowDoc.nodes,
            edges: flowDoc.edges,
            meta: flowDoc.meta,
            yamlCanonical: canonical,
            yamlDraft: canonical,
            syncSource: "yaml",
            parseError: null,
            statusMessage: "YAML applied",
            isDirty: canonical !== currentState.persistedYaml,
            ...historyState,
          };
        });
        return true;
      } catch (error) {
        set({
          parseError: error instanceof Error ? error.message : "Failed to parse YAML draft.",
          statusMessage: null,
        });
        return false;
      }
    },

    setCanvasCanonicalYaml: (yaml) => {
      set((state) => ({
        yamlCanonical: yaml,
        yamlDraft: state.syncSource === "canvas" ? yaml : state.yamlDraft,
        statusMessage: null,
        isDirty: yaml !== state.persistedYaml,
        parseError: null,
      }));
    },

    markSaved: () => {
      set((state) => ({
        persistedYaml: state.yamlCanonical,
        yamlDraft: state.yamlCanonical,
        isDirty: false,
        parseError: null,
        statusMessage: "Scenario saved",
      }));
    },

    reset: () => {
      set({
        ...baseSnapshot(),
        parseError: null,
        statusMessage: null,
        historyPast: [],
        historyFuture: [],
        canUndo: false,
        canRedo: false,
      });
    },
  };
}

