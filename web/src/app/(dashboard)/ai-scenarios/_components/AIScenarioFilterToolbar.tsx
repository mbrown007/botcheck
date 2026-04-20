"use client";

import { ChevronDown, FolderTree, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

export interface AIScenarioNamespaceOption {
  label: string;
  value: string;
  count: number;
}

interface AIScenarioFilterToolbarProps {
  searchQuery: string;
  selectedNamespace: string | null;
  selectedNamespaceLabel: string;
  namespaceOptions: AIScenarioNamespaceOption[];
  totalScenarios: number;
  hasActiveFilters: boolean;
  filterSummary: string;
  onSearchQueryChange: (value: string) => void;
  onSelectNamespace: (value: string | null) => void;
  onClearFilters: () => void;
}

export function AIScenarioFilterToolbar({
  searchQuery,
  selectedNamespace,
  selectedNamespaceLabel,
  namespaceOptions,
  totalScenarios,
  hasActiveFilters,
  filterSummary,
  onSearchQueryChange,
  onSelectNamespace,
  onClearFilters,
}: AIScenarioFilterToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative min-w-[200px] max-w-xs flex-1">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
        <input
          id="ai-scenario-search-input"
          data-testid="ai-scenario-search-input"
          type="search"
          value={searchQuery}
          onChange={(e) => onSearchQueryChange(e.target.value)}
          placeholder="Search name, id, namespace…"
          className="w-full rounded-md border border-border bg-bg-surface py-2 pl-9 pr-3 text-sm text-text-primary placeholder:text-text-muted focus:border-border-focus focus:outline-none"
        />
      </div>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="secondary"
            size="md"
            data-testid="ai-scenario-namespace-filter-trigger"
            className={cn(selectedNamespace && "border-brand text-text-primary")}
          >
            <FolderTree className="size-4" />
            {selectedNamespaceLabel}
            <ChevronDown className="size-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-56">
          <DropdownMenuItem
            onSelect={() => onSelectNamespace(null)}
            className="flex items-center justify-between"
          >
            <span className={cn(!selectedNamespace && "font-medium text-text-primary")}>
              All namespaces
            </span>
            <span className="font-mono text-xs text-text-muted">{totalScenarios}</span>
          </DropdownMenuItem>
          {namespaceOptions.map((opt) => (
            <DropdownMenuItem
              key={opt.value}
              onSelect={() => onSelectNamespace(opt.value)}
              className="flex items-center justify-between"
            >
              <span
                className={cn(selectedNamespace === opt.value && "font-medium text-text-primary")}
              >
                {opt.label}
              </span>
              <span className="font-mono text-xs text-text-muted">{opt.count}</span>
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>

      {hasActiveFilters ? (
        <div className="flex flex-wrap items-center gap-1.5">
          {selectedNamespace ? (
            <button
              type="button"
              onClick={() => onSelectNamespace(null)}
              className="inline-flex items-center gap-1.5 rounded-full border border-brand/40 bg-brand/10 px-2.5 py-1 text-xs text-text-primary transition-colors hover:bg-brand/20"
            >
              <FolderTree className="size-3" />
              {selectedNamespaceLabel}
              <X className="size-3 text-text-muted" />
            </button>
          ) : null}
          {searchQuery.trim() ? (
            <button
              type="button"
              onClick={() => onSearchQueryChange("")}
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-bg-elevated px-2.5 py-1 text-xs text-text-secondary transition-colors hover:bg-bg-surface"
            >
              &ldquo;{searchQuery.trim()}&rdquo;
              <X className="size-3 text-text-muted" />
            </button>
          ) : null}
          <button
            type="button"
            onClick={onClearFilters}
            className="text-xs text-text-muted transition-colors hover:text-text-primary"
          >
            Clear all
          </button>
        </div>
      ) : null}

      <span className="ml-auto whitespace-nowrap text-sm text-text-muted">{filterSummary}</span>
    </div>
  );
}
