"use client";

import React from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface MetadataFieldLabelProps {
  label: string;
  help: string;
}

export function MetadataFieldLabel({ label, help }: MetadataFieldLabelProps) {
  return (
    <span className="inline-flex items-center gap-1">
      <span>{label}</span>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            aria-label={`${label} help`}
            onClick={(event) => event.preventDefault()}
            className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full border border-border text-[9px] font-semibold text-text-muted hover:text-text-primary focus:outline-none focus:ring-1 focus:ring-border-focus"
          >
            ?
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[280px] text-[11px] leading-4">
          {help}
        </TooltipContent>
      </Tooltip>
    </span>
  );
}
