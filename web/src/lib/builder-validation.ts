import type { BuilderEdge, BuilderNode } from "@/lib/flow-translator";
import type { ScenarioValidationError } from "@/lib/api/types";
import {
  getBuilderTimeRouteTimezone,
  getBuilderTimeRouteWindows,
  getBuilderTurnBranchCases,
  getBuilderTurnBranchMode,
  getBuilderTurnAudioFile,
  getBuilderTurnDtmf,
  getBuilderTurnKind,
  getBuilderTurnSilenceS,
  getBuilderTurnSpeaker,
  getBuilderTurnText,
} from "@/lib/builder-types";
import {
  normalizeTurnId,
  parseScenarioYaml,
  parseTurns,
} from "@/lib/flow-translator/shared";
import { inferDecisionSlotFromEdge } from "@/lib/builder-decision";
import { decisionPathSlot, isDefaultDecisionSlot } from "@/lib/decision-slots";

export type NodeStructuralErrors = Record<string, string[]>;

export const TIME_ROUTE_HHMM_RE = /^(?:[01]\d|2[0-3]):[0-5]\d$/;

function edgeCondition(edge: BuilderEdge): string {
  if (typeof edge.data?.condition === "string") {
    return edge.data.condition.trim();
  }
  if (typeof edge.label === "string") {
    return edge.label.trim();
  }
  return "";
}

function isDefaultCondition(condition: string): boolean {
  return isDefaultDecisionSlot(condition);
}

function addNodeError(
  errors: NodeStructuralErrors,
  nodeId: string,
  message: string
): void {
  if (!errors[nodeId]) {
    errors[nodeId] = [];
  }
  if (!errors[nodeId]?.includes(message)) {
    errors[nodeId]?.push(message);
  }
}

function uniqueMessages(messages: string[]): string[] {
  const seen = new Set<string>();
  return messages.filter((message) => {
    const normalized = message.trim();
    if (!normalized || seen.has(normalized)) {
      return false;
    }
    seen.add(normalized);
    return true;
  });
}

function turnIdsFromYaml(yaml: string): string[] {
  const scenario = parseScenarioYaml(yaml);
  const turns = parseTurns(scenario.turns);
  return turns.map((turn, index) => normalizeTurnId(turn, index));
}

export function describeScenarioValidationErrors(
  validationErrors: ScenarioValidationError[],
  yaml: string
): { saveError: string; nodeErrors: NodeStructuralErrors } {
  const nodeErrors: NodeStructuralErrors = {};
  const detailLines: string[] = [];
  let turnIds: string[] = [];

  try {
    turnIds = turnIdsFromYaml(yaml);
  } catch {
    turnIds = [];
  }

  for (const validationError of validationErrors) {
    const field = validationError.field.trim();
    const message = validationError.message.trim() || "Validation failed.";
    const turnMatch = /^turns\.(\d+)(?:\.|$)/.exec(field);
    if (turnMatch) {
      const turnIndex = Number(turnMatch[1]);
      const turnId = turnIndex < turnIds.length ? turnIds[turnIndex] : undefined;
      if (turnId) {
        addNodeError(nodeErrors, turnId, message);
        detailLines.push(`${turnId}: ${message}`);
        continue;
      }
    }
    detailLines.push(field ? `${field}: ${message}` : message);
  }

  const uniqueLines = uniqueMessages(detailLines);
  const visibleLines = uniqueLines.slice(0, 6);
  const remainingCount = uniqueLines.length - visibleLines.length;
  const summary =
    visibleLines.length > 0
      ? [
          "Validation failed. Fix scenario errors before saving.",
          ...visibleLines.map((line) => `- ${line}`),
          ...(remainingCount > 0 ? [`- ${remainingCount} more issue${remainingCount === 1 ? "" : "s"}`] : []),
        ].join("\n")
      : "Validation failed. Fix scenario errors before saving.";

  return {
    saveError: summary,
    nodeErrors,
  };
}

export function computeNodeStructuralErrors(
  nodes: BuilderNode[],
  edges: BuilderEdge[]
): NodeStructuralErrors {
  const errors: NodeStructuralErrors = {};
  const idCounts = new Map<string, number>();

  for (const node of nodes) {
    const trimmedId = node.id.trim();
    if (!trimmedId) {
      addNodeError(errors, node.id, "Turn ID cannot be empty.");
      continue;
    }
    idCounts.set(trimmedId, (idCounts.get(trimmedId) ?? 0) + 1);
  }

  for (const node of nodes) {
    const duplicateCount = idCounts.get(node.id.trim()) ?? 0;
    if (duplicateCount > 1) {
      addNodeError(errors, node.id, "Duplicate turn ID.");
    }
    const turn = node.data.turn;
    const speaker = getBuilderTurnSpeaker(turn);
    const kind = getBuilderTurnKind(turn);
    if (kind === "time_route") {
      const timezone = getBuilderTimeRouteTimezone(turn)?.trim() ?? "";
      if (!timezone) {
        addNodeError(errors, node.id, "Time route requires a timezone.");
      }
      const windows = getBuilderTimeRouteWindows(turn);
      if (windows.length === 0) {
        addNodeError(errors, node.id, "Time route requires at least one window.");
      }
      windows.forEach((window, index) => {
        const label = typeof window.label === "string" && window.label.trim()
          ? window.label.trim()
          : `path_${index + 1}`;
        const start = typeof window.start === "string" ? window.start.trim() : "";
        const end = typeof window.end === "string" ? window.end.trim() : "";
        if (!TIME_ROUTE_HHMM_RE.test(start)) {
          addNodeError(
            errors,
            node.id,
            `Time route window "${label}" requires start in HH:MM format.`
          );
        }
        if (!TIME_ROUTE_HHMM_RE.test(end)) {
          addNodeError(
            errors,
            node.id,
            `Time route window "${label}" requires end in HH:MM format.`
          );
        }
        if (start && end && start === end) {
          addNodeError(
            errors,
            node.id,
            `Time route window "${label}" cannot use the same start and end time.`
          );
        }
      });
    } else if (speaker === "harness" && kind !== "hangup" && kind !== "wait") {
      const hasPromptText = getBuilderTurnText(turn).trim().length > 0;
      const audioFile = getBuilderTurnAudioFile(turn);
      const dtmf = getBuilderTurnDtmf(turn);
      const silenceS = getBuilderTurnSilenceS(turn);
      const hasAudio = typeof audioFile === "string" && audioFile.trim().length > 0;
      const hasDtmf = typeof dtmf === "string" && dtmf.trim().length > 0;
      const hasSilence = typeof silenceS === "number" && silenceS > 0;
      if (!hasPromptText && !hasAudio && !hasDtmf && !hasSilence) {
        addNodeError(
          errors,
          node.id,
          "Harness turn requires text, audio_file, dtmf, or silence_s."
        );
      }
    }
  }

  const edgesBySource = new Map<string, BuilderEdge[]>();
  const nodesById = new Map(nodes.map((node) => [node.id, node] as const));
  for (const edge of edges) {
    if (!edgesBySource.has(edge.source)) {
      edgesBySource.set(edge.source, []);
    }
    edgesBySource.get(edge.source)?.push(edge);
    if (!edge.target.trim()) {
      addNodeError(errors, edge.source, "Edge target is required.");
    }
  }

  for (const [sourceId, sourceEdges] of edgesBySource) {
    if (sourceEdges.length <= 1) {
      continue;
    }
    const defaultEdges = sourceEdges.filter((edge) =>
      isDefaultCondition(edgeCondition(edge))
    );
    if (defaultEdges.length === 0) {
      addNodeError(errors, sourceId, "Multi-exit turns require one default edge.");
    }
    if (defaultEdges.length > 1) {
      addNodeError(errors, sourceId, "Only one default edge is allowed.");
    }

    const seenConditions = new Set<string>();
    for (const edge of sourceEdges) {
      const condition = edgeCondition(edge);
      if (!condition || isDefaultCondition(condition)) {
        continue;
      }
      const normalized = condition.toLowerCase();
      if (seenConditions.has(normalized)) {
        addNodeError(errors, sourceId, `Duplicate branch condition: "${condition}".`);
        continue;
      }
      seenConditions.add(normalized);
    }

    const sourceNode = nodesById.get(sourceId);
    if (!sourceNode) {
      continue;
    }
    const branchMode = getBuilderTurnBranchMode(sourceNode.data.turn);
    if (branchMode === "classifier") {
      continue;
    }
    const casesBySlot = new Map(
      getBuilderTurnBranchCases(sourceNode.data.turn).map((entry, index) => [
        decisionPathSlot(index + 1),
        entry,
      ])
    );
    for (const edge of sourceEdges) {
      const slot = inferDecisionSlotFromEdge(edge);
      if (!slot || isDefaultDecisionSlot(slot)) {
        continue;
      }
      const branchCase = casesBySlot.get(slot);
      if (branchMode === "keyword") {
        const match = typeof branchCase?.match === "string" ? branchCase.match.trim() : "";
        if (!match) {
          addNodeError(
            errors,
            sourceId,
            `Branch "${edgeCondition(edge)}" requires a keyword match.`
          );
        }
        continue;
      }
      const pattern = typeof branchCase?.regex === "string" ? branchCase.regex.trim() : "";
      if (!pattern) {
        addNodeError(errors, sourceId, `Branch "${edgeCondition(edge)}" requires a regex.`);
        continue;
      }
      try {
        new RegExp(pattern, "i");
      } catch {
        addNodeError(errors, sourceId, `Branch "${edgeCondition(edge)}" has an invalid regex.`);
      }
    }
  }

  return errors;
}
