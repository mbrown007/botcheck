import {
  getBuilderTimeRouteTimezone,
  getBuilderTimeRouteWindows,
  getBuilderTurnBranchMode,
  getBuilderTurnSpeaker,
  getBuilderTurnText,
  getBuilderTurnWaitS,
  getBuilderTurnBranchCases,
  toCanonicalBuilderTurn,
  type BuilderTurn,
} from "@/lib/builder-types";
import { decisionPathSlot } from "@/lib/decision-slots";

export interface BuilderNodeData {
  [key: string]: unknown;
  turnId: string;
  orderIndex: number;
  speaker: "harness" | "bot";
  text: string;
  turn: BuilderTurn;
  isBranchDecision?: boolean;
  branchOutputCount?: number;
  decisionOutputLabels?: Record<string, string>;
  branchMode?: "classifier" | "keyword" | "regex";
  branchCaseRules?: Record<string, { match?: string; regex?: string }>;
  turnCacheStatus?: "cached" | "skipped" | "failed" | "unknown";
  turnCacheKey?: string | null;
  turnCacheBucketName?: string | null;
  onDecisionOutputCountChange?: (nextCount: number) => void;
  onDecisionSlotLabelChange?: (slot: string, label: string) => void;
  nodeErrors?: string[];
  onToast?: (message: string, tone?: "info" | "warn" | "error") => void;
}

export interface NodeTypeDescriptor {
  type: string;
  label: string;
  paletteColor: string;
  toYaml: (data: BuilderNodeData) => BuilderTurn;
  fromYaml: (turn: BuilderTurn, orderIndex: number) => BuilderNodeData;
}

const nodeRegistry = new Map<string, NodeTypeDescriptor>();

function registerNodeType(descriptor: NodeTypeDescriptor): void {
  nodeRegistry.set(descriptor.type, descriptor);
}

export function getNodeDescriptor(type: string): NodeTypeDescriptor | undefined {
  return nodeRegistry.get(type);
}

export function branchCaseRulesForTurn(
  turn: BuilderTurn
): Record<string, { match?: string; regex?: string }> {
  const rules: Record<string, { match?: string; regex?: string }> = {};
  const cases = getBuilderTurnBranchCases(turn);
  cases.forEach((entry, index) => {
    const slot = decisionPathSlot(index + 1);
    const next: { match?: string; regex?: string } = {};
    if (typeof entry.match === "string" && entry.match.trim()) {
      next.match = entry.match.trim();
    }
    if (typeof entry.regex === "string" && entry.regex.trim()) {
      next.regex = entry.regex.trim();
    }
    if (next.match || next.regex) {
      rules[slot] = next;
    }
  });
  return rules;
}

const harnessNodeDescriptor: NodeTypeDescriptor = {
  type: "harnessNode",
  label: "Harness",
  paletteColor: "bg-brand-muted",
  toYaml: (data) => toCanonicalBuilderTurn(data.turn),
  fromYaml: (turn, orderIndex) => ({
    turnId: String(turn.id),
    orderIndex,
    speaker: getBuilderTurnSpeaker(turn),
    text: getBuilderTurnText(turn),
    branchMode: getBuilderTurnBranchMode(turn),
    branchCaseRules: branchCaseRulesForTurn(turn),
    turn: { ...turn },
  }),
};

registerNodeType(harnessNodeDescriptor);

const botNodeDescriptor: NodeTypeDescriptor = {
  type: "botNode",
  label: "Bot",
  paletteColor: "bg-bg-elevated",
  toYaml: (data) => toCanonicalBuilderTurn(data.turn),
  fromYaml: (turn, orderIndex) => ({
    turnId: String(turn.id),
    orderIndex,
    speaker: "bot",
    text: getBuilderTurnText(turn),
    branchMode: getBuilderTurnBranchMode(turn),
    branchCaseRules: branchCaseRulesForTurn(turn),
    turn: { ...turn },
  }),
};

registerNodeType(botNodeDescriptor);

const hangupNodeDescriptor: NodeTypeDescriptor = {
  type: "hangupNode",
  label: "Hangup",
  paletteColor: "bg-fail-bg",
  toYaml: (data) => toCanonicalBuilderTurn(data.turn),
  fromYaml: (turn, orderIndex) => ({
    turnId: String(turn.id),
    orderIndex,
    speaker: "harness" as const,
    text: "",
    branchMode: "classifier" as const,
    branchCaseRules: {},
    turn: {
      ...turn,
      kind: "hangup" as const,
    },
  }),
};

registerNodeType(hangupNodeDescriptor);

const waitNodeDescriptor: NodeTypeDescriptor = {
  type: "waitNode",
  label: "Wait",
  paletteColor: "bg-amber-100",
  toYaml: (data) => toCanonicalBuilderTurn(data.turn),
  fromYaml: (turn, orderIndex) => ({
    turnId: String(turn.id),
    orderIndex,
    speaker: "harness" as const,
    text: "",
    branchMode: "classifier" as const,
    branchCaseRules: {},
    turn: {
      ...turn,
      kind: "wait" as const,
      wait_s: typeof getBuilderTurnWaitS(turn) === "number" ? getBuilderTurnWaitS(turn) : 1,
    },
  }),
};

registerNodeType(waitNodeDescriptor);

const timeRouteNodeDescriptor: NodeTypeDescriptor = {
  type: "timeRouteNode",
  label: "Time Route",
  paletteColor: "bg-sky-100",
  toYaml: (data) => toCanonicalBuilderTurn(data.turn),
  fromYaml: (turn, orderIndex) => {
    const windows = getBuilderTimeRouteWindows(turn);
    const decisionOutputLabels: Record<string, string> = {};
    windows.forEach((window, index) => {
      if (typeof window.label === "string" && window.label.trim()) {
        decisionOutputLabels[decisionPathSlot(index + 1)] = window.label.trim();
      }
    });
    return {
      turnId: String(turn.id),
      orderIndex,
      speaker: "harness" as const,
      text: "",
      isBranchDecision: true,
      branchOutputCount: Math.max(1, windows.length + 1),
      decisionOutputLabels,
      turn: {
        ...turn,
        kind: "time_route" as const,
        timezone: getBuilderTimeRouteTimezone(turn) ?? "UTC",
        windows: windows.map((window) => ({
          label: window.label ?? "",
          start: window.start ?? "",
          end: window.end ?? "",
          next: window.next ?? "",
        })),
        default: typeof turn.default === "string" ? turn.default : "",
      },
    };
  },
};

registerNodeType(timeRouteNodeDescriptor);
