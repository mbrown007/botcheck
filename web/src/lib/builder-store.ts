import { create } from "zustand";
import { createCanvasSlice } from "@/lib/builder-store/canvas-slice";
import { createHistorySlice } from "@/lib/builder-store/history-slice";
import { createIoSlice } from "@/lib/builder-store/io-slice";
import { baseSnapshot } from "@/lib/builder-store/snapshot";
import type { BuilderState } from "@/lib/builder-store/types";

export const useBuilderStore = create<BuilderState>((set, get) => ({
  ...baseSnapshot(),
  ...createIoSlice(set, get),
  ...createHistorySlice(set),
  ...createCanvasSlice(set),
}));
