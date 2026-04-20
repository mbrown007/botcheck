import type { BuilderState, BuilderStoreSet } from "./types";
import { withHistoryPush } from "./history-utils";
import { createSnapshot } from "./snapshot";

type HistorySlice = Pick<
  BuilderState,
  "historyPast" | "historyFuture" | "canUndo" | "canRedo" | "checkpoint" | "undo" | "redo"
>;

export function createHistorySlice(set: BuilderStoreSet): HistorySlice {
  return {
    historyPast: [],
    historyFuture: [],
    canUndo: false,
    canRedo: false,

    checkpoint: () => {
      set((state) => {
        const snapshot = createSnapshot(state);
        const historyState = withHistoryPush(state, snapshot);
        return {
          ...historyState,
        };
      });
    },

    undo: () => {
      set((state) => {
        if (state.historyPast.length === 0) {
          return {};
        }
        const previous = state.historyPast[state.historyPast.length - 1];
        const historyPast = state.historyPast.slice(0, -1);
        const historyFuture = [...state.historyFuture, createSnapshot(state)];
        return {
          ...createSnapshot(previous),
          parseError: null,
          statusMessage: null,
          historyPast,
          historyFuture,
          canUndo: historyPast.length > 0,
          canRedo: historyFuture.length > 0,
        };
      });
    },

    redo: () => {
      set((state) => {
        if (state.historyFuture.length === 0) {
          return {};
        }
        const next = state.historyFuture[state.historyFuture.length - 1];
        const historyFuture = state.historyFuture.slice(0, -1);
        const historyPast = [...state.historyPast, createSnapshot(state)];
        return {
          ...createSnapshot(next),
          parseError: null,
          statusMessage: null,
          historyPast,
          historyFuture,
          canUndo: historyPast.length > 0,
          canRedo: historyFuture.length > 0,
        };
      });
    },
  };
}
