"use client";

import { useCallback, useRef } from "react";

import type { BuilderPaletteBlockKind } from "@/lib/builder-blocks";
import type { BuilderCanvasHandle } from "../_components/BuilderCanvas";

export function useBuilderCanvasInteractions() {
  const canvasRef = useRef<BuilderCanvasHandle | null>(null);

  const handleCopySelectedBlock = useCallback(() => {
    canvasRef.current?.copySelected();
  }, []);

  const handlePasteCopiedBlock = useCallback(() => {
    canvasRef.current?.pasteClipboard();
  }, []);

  const handleDeleteSelectedBlocks = useCallback(() => {
    canvasRef.current?.deleteSelected();
  }, []);

  const handleInsertBlock = useCallback((kind: BuilderPaletteBlockKind) => {
    canvasRef.current?.quickAddBlock(kind);
  }, []);

  return {
    canvasRef,
    handleCopySelectedBlock,
    handleDeleteSelectedBlocks,
    handleInsertBlock,
    handlePasteCopiedBlock,
  };
}
