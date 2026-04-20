"use client";

import React from "react";
import { AlertCircle, Inbox, LoaderCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type TableStateKind = "loading" | "empty" | "error";

interface TableStateProps {
  kind: TableStateKind;
  title?: string;
  message: string;
  columns?: number;
  rows?: number;
  className?: string;
}

export function TableState({
  kind,
  title,
  message,
  columns = 5,
  rows = 5,
  className,
}: TableStateProps) {
  if (kind === "loading") {
    return (
      <div className={cn("px-5 py-4", className)}>
        <div className="mb-4 flex items-center gap-2 text-sm text-text-muted">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          <span>{message}</span>
        </div>
        <div className="space-y-3">
          {Array.from({ length: rows }).map((_, rowIndex) => (
            <div
              key={`table-skeleton-row-${rowIndex}`}
              className="grid gap-3"
              style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
            >
              {Array.from({ length: columns }).map((__, columnIndex) => (
                <div
                  key={`table-skeleton-cell-${rowIndex}-${columnIndex}`}
                  className={cn(
                    "h-4 animate-pulse rounded-full bg-bg-elevated",
                    columnIndex === 0 && "w-[92%]",
                    columnIndex > 0 && columnIndex < columns - 1 && "w-[80%]",
                    columnIndex === columns - 1 && "w-[64%]"
                  )}
                />
              ))}
            </div>
          ))}
        </div>
      </div>
    );
  }

  const Icon = kind === "error" ? AlertCircle : Inbox;

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 px-5 py-10 text-center",
        className
      )}
    >
      <div
        className={cn(
          "flex h-11 w-11 items-center justify-center rounded-full border",
          kind === "error"
            ? "border-fail-border bg-fail-bg text-fail"
            : "border-border bg-bg-elevated text-text-muted"
        )}
      >
        <Icon className="h-5 w-5" />
      </div>
      <div className="space-y-1">
        <p
          className={cn(
            "text-sm font-medium",
            kind === "error" ? "text-fail" : "text-text-primary"
          )}
        >
          {title ?? (kind === "error" ? "Unable to load data" : "Nothing to show")}
        </p>
        <p className="max-w-[460px] text-sm text-text-muted">{message}</p>
      </div>
    </div>
  );
}
