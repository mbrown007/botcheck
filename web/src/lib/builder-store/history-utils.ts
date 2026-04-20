import type { BuilderHistoryState, BuilderSnapshot } from "./types";
import { createSnapshot } from "./snapshot";

const MAX_HISTORY = 60;

type HistoryPushState = Pick<BuilderHistoryState, "historyPast" | "historyFuture">;

export function withHistoryPush(
  state: HistoryPushState,
  snapshot: BuilderSnapshot
): BuilderHistoryState {
  const previous = state.historyPast[state.historyPast.length - 1];
  if (previous) {
    const previousSignature = JSON.stringify(previous);
    const nextSignature = JSON.stringify(snapshot);
    if (previousSignature === nextSignature) {
      return {
        historyPast: state.historyPast,
        historyFuture: state.historyFuture,
        canUndo: state.historyPast.length > 0,
        canRedo: state.historyFuture.length > 0,
      };
    }
  }

  const nextPast = [...state.historyPast, createSnapshot(snapshot)];
  const clippedPast =
    nextPast.length > MAX_HISTORY ? nextPast.slice(nextPast.length - MAX_HISTORY) : nextPast;
  return {
    historyPast: clippedPast,
    historyFuture: [],
    canUndo: clippedPast.length > 0,
    canRedo: false,
  };
}

