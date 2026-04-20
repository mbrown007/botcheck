import type { BuilderState, BuilderStoreSet } from "./types";
import { withHistoryPush } from "./history-utils";
import { createSnapshot, cloneMeta } from "./snapshot";
import {
  getBuilderTurnBranchMode,
  getBuilderTurnSpeaker,
  getBuilderTurnText,
  toCanonicalBuilderTurn,
} from "@/lib/builder-types";
import { branchCaseRulesForTurn } from "@/lib/node-registry";
import { selectNodeTypeForTurn } from "@/lib/node-type-selector";

type CanvasSlice = Pick<
  BuilderState,
  "updateNodesFromCanvas" | "updateEdgesFromCanvas" | "updateNodeTurn" | "updateMeta"
>;

export function createCanvasSlice(set: BuilderStoreSet): CanvasSlice {
  return {
    updateNodesFromCanvas: (nodes) => {
      set((state) => ({
        nodes,
        syncSource: "canvas",
        statusMessage: null,
        isDirty: state.yamlCanonical !== state.persistedYaml || state.isDirty,
        parseError: null,
      }));
    },

    updateEdgesFromCanvas: (edges) => {
      set((state) => ({
        edges,
        syncSource: "canvas",
        statusMessage: null,
        isDirty: state.yamlCanonical !== state.persistedYaml || state.isDirty,
        parseError: null,
      }));
    },

    updateNodeTurn: (nodeId, nextTurn) => {
      set((state) => {
        const snapshot = createSnapshot(state);
        const historyState = withHistoryPush(state, snapshot);
        const canonicalTurn = toCanonicalBuilderTurn(nextTurn);
        const nextNodes = state.nodes.map((node) => {
          if (node.id !== nodeId) {
            return node;
          }
          return {
            ...node,
            type: selectNodeTypeForTurn(canonicalTurn),
            data: {
              // Preserve all existing node data (isBranchDecision, branchOutputCount,
              // decisionOutputLabels, cache status, callbacks, etc.) then overwrite only
              // the fields that are derived from the turn content.
              // NOTE: branchOutputCount and isBranchDecision are NOT recomputed here.
              // Callers that change the number of branching cases must update those
              // fields separately via onDecisionOutputCountChange.
              ...node.data,
              turnId: nodeId,
              text: getBuilderTurnText(canonicalTurn),
              speaker: getBuilderTurnSpeaker(canonicalTurn),
              branchMode: getBuilderTurnBranchMode(canonicalTurn),
              branchCaseRules: branchCaseRulesForTurn(canonicalTurn),
              turn: { ...canonicalTurn },
            },
          };
        });
        return {
          nodes: nextNodes,
          syncSource: "canvas",
          statusMessage: null,
          isDirty: true,
          parseError: null,
          ...historyState,
        };
      });
    },

    updateMeta: (nextMeta) => {
      set(() => ({
        meta: cloneMeta(nextMeta),
        syncSource: "canvas",
        statusMessage: null,
        isDirty: true,
        parseError: null,
      }));
    },
  };
}
