"use client";

import { useEffect } from "react";

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  if (target.isContentEditable) {
    return true;
  }
  const tag = target.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select";
}

export interface BuilderKeyboardOptions {
  canSave: boolean;
  handleSave: () => Promise<void>;
  handleCopySelectedBlock: () => void;
  handlePasteCopiedBlock: () => void;
  handleDeleteSelectedBlocks: () => void;
  undo: () => void;
  redo: () => void;
}

export function useBuilderKeyboard({
  canSave,
  handleSave,
  handleCopySelectedBlock,
  handlePasteCopiedBlock,
  handleDeleteSelectedBlocks,
  undo,
  redo,
}: BuilderKeyboardOptions) {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const key = event.key.toLowerCase();
      if (!isTypingTarget(event.target) && (key === "delete" || key === "backspace")) {
        event.preventDefault();
        handleDeleteSelectedBlocks();
        return;
      }
      if (!(event.metaKey || event.ctrlKey)) {
        return;
      }
      if (key === "s") {
        if (!canSave) {
          return;
        }
        event.preventDefault();
        void handleSave();
        return;
      }
      if (isTypingTarget(event.target)) {
        return;
      }
      if (key === "z" && event.shiftKey) {
        event.preventDefault();
        redo();
        return;
      }
      if (key === "c") {
        event.preventDefault();
        handleCopySelectedBlock();
        return;
      }
      if (key === "v") {
        event.preventDefault();
        handlePasteCopiedBlock();
        return;
      }
      if (key === "z") {
        event.preventDefault();
        undo();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [
    handleCopySelectedBlock,
    canSave,
    handleDeleteSelectedBlocks,
    handlePasteCopiedBlock,
    handleSave,
    redo,
    undo,
  ]);
}
