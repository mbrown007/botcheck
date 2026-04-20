"use client";

import { Edit3, Eye, ListTree, Trash2 } from "lucide-react";
import type { AIScenarioSummary } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { NamespacePath } from "@/components/scenarios/namespace-path";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { formatTs } from "./format";

interface AIScenarioCatalogTableProps {
  scenarios: AIScenarioSummary[] | undefined;
  personaNameById: Map<string, string>;
  selectedAIScenarioId: string | null;
  detailAIScenarioId: string | null;
  deletingAIScenarioId: string | null;
  editingAIScenarioId: string | null;
  onViewAIScenario: (aiScenarioId: string) => void;
  onEditAIScenario: (aiScenarioId: string) => void;
  onToggleRecords: (aiScenarioId: string) => void;
  onDeleteAIScenario: (aiScenarioId: string) => void;
}

export function AIScenarioCatalogTable({
  scenarios,
  personaNameById,
  selectedAIScenarioId,
  detailAIScenarioId,
  deletingAIScenarioId,
  editingAIScenarioId,
  onViewAIScenario,
  onEditAIScenario,
  onToggleRecords,
  onDeleteAIScenario,
}: AIScenarioCatalogTableProps) {
  return (
    <TooltipProvider delayDuration={120}>
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-border text-text-muted text-xs uppercase tracking-wide">
          <th className="px-5 py-3 text-left font-medium">Scenario</th>
          <th className="px-5 py-3 text-left font-medium">Persona</th>
          <th className="px-5 py-3 text-left font-medium">Opening</th>
          <th className="px-5 py-3 text-left font-medium">Records</th>
          <th className="px-5 py-3 text-left font-medium">Status</th>
          <th className="px-5 py-3 text-left font-medium">Updated</th>
          <th className="px-5 py-3 text-right font-medium">Actions</th>
        </tr>
      </thead>
      <tbody>
        {scenarios?.map((row) => (
          <tr key={row.ai_scenario_id} className="border-b border-border last:border-0">
            <td className="px-5 py-3">
              <div className="mb-1">
                <NamespacePath namespace={row.namespace} compact />
              </div>
              <p className="font-medium text-text-primary">{row.name}</p>
              <p className="font-mono text-[11px] text-text-muted">{row.ai_scenario_id}</p>
            </td>
            <td className="px-5 py-3 text-text-secondary">
              {personaNameById.get(row.persona_id) ?? row.persona_id}
            </td>
            <td className="px-5 py-3 text-text-secondary">
              {row.opening_strategy === "wait_for_bot_greeting" ? "Wait for bot" : "Caller opens"}
            </td>
            <td className="px-5 py-3 font-mono text-xs text-text-secondary">{row.record_count}</td>
            <td className="px-5 py-3 text-xs text-text-secondary">
              {row.is_active ? "Active" : "Inactive"}
            </td>
            <td className="px-5 py-3 text-xs text-text-muted">{formatTs(row.updated_at)}</td>
            <td className="px-5 py-3 text-right">
              <div className="inline-flex flex-wrap justify-end gap-2">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      data-testid={`ai-scenario-view-${row.ai_scenario_id}`}
                      aria-label="View"
                      size="icon"
                      variant={detailAIScenarioId === row.ai_scenario_id ? "primary" : "secondary"}
                      onClick={() => onViewAIScenario(row.ai_scenario_id)}
                    >
                      <Eye className="h-3.5 w-3.5" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    {detailAIScenarioId === row.ai_scenario_id ? "Hide Detail" : "View"}
                  </TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      data-testid={`ai-scenario-records-toggle-${row.ai_scenario_id}`}
                      aria-label="Records"
                      size="icon"
                      variant={selectedAIScenarioId === row.ai_scenario_id ? "primary" : "secondary"}
                      onClick={() => onToggleRecords(row.ai_scenario_id)}
                    >
                      <ListTree className="h-3.5 w-3.5" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    {selectedAIScenarioId === row.ai_scenario_id ? "Hide Records" : "Records"}
                  </TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      data-testid={`ai-scenario-edit-${row.ai_scenario_id}`}
                      aria-label="Edit"
                      size="icon"
                      variant="secondary"
                      onClick={() => onEditAIScenario(row.ai_scenario_id)}
                      disabled={editingAIScenarioId === row.ai_scenario_id}
                    >
                      <Edit3 className="h-3.5 w-3.5" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    {editingAIScenarioId === row.ai_scenario_id ? "Loading Edit" : "Edit"}
                  </TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      aria-label="Delete"
                      size="icon"
                      variant="secondary"
                      onClick={() => onDeleteAIScenario(row.ai_scenario_id)}
                      disabled={deletingAIScenarioId === row.ai_scenario_id}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    {deletingAIScenarioId === row.ai_scenario_id ? "Deleting" : "Delete"}
                  </TooltipContent>
                </Tooltip>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
    </TooltipProvider>
  );
}
