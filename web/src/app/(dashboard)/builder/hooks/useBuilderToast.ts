"use client";

import { useCallback, useRef, useState } from "react";

export type BuilderToast = {
  id: number;
  tone: "info" | "warn" | "error";
  message: string;
};

export type PushToast = (message: string, tone?: "info" | "warn" | "error") => void;

export function useBuilderToast() {
  const [toasts, setToasts] = useState<BuilderToast[]>([]);
  const toastSeqRef = useRef(0);

  const pushToast = useCallback<PushToast>(
    (message, tone = "info") => {
      toastSeqRef.current += 1;
      const nextId = toastSeqRef.current;
      setToasts((current) => [...current, { id: nextId, tone, message }]);
      window.setTimeout(() => {
        setToasts((current) => current.filter((entry) => entry.id !== nextId));
      }, 4500);
    },
    []
  );

  return { toasts, pushToast };
}
