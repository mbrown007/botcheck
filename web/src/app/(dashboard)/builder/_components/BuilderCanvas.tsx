"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import {
  Background,
  BackgroundVariant,
  Controls,
  ReactFlow,
  applyEdgeChanges,
  applyNodeChanges,
  useReactFlow,
  type Connection,
  type EdgeChange,
  type EdgeTypes,
  type NodeChange,
  type NodeTypes,
} from "@xyflow/react";
import {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useMemo,
  useState,
  type DragEvent as ReactDragEvent,
} from "react";
import { useTheme } from "next-themes";
import { useForm } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { useBuilderStore } from "@/lib/builder-store";
import { HarnessNode } from "@/components/builder/harness-node";
import { BotNode } from "@/components/builder/bot-node";
import { HangupNode } from "@/components/builder/hangup-node";
import { TimeRouteNode } from "@/components/builder/time-route-node";
import { WaitNode } from "@/components/builder/wait-node";
import { BranchingEdge } from "@/components/builder/branching-edge";
import { computeNodeStructuralErrors } from "@/lib/builder-validation";
import type { NodeStructuralErrors } from "@/lib/builder-validation";
import {
  connectWithBranchingRules,
  edgeCondition,
  removeEdgeWithRebalance,
  shouldPromptForBranchCondition,
  updateEdgeCondition,
} from "@/lib/builder-edges";
import {
  BRANCH_CASE_COUNT_DEFAULT,
  BUILDER_BLOCK_DND_MIME,
  clampBranchCaseCount,
  deleteBlocksByNodeIds,
  duplicateTurnBlock,
  insertPaletteBlock,
  type BuilderPaletteBlockKind,
} from "@/lib/builder-blocks";
import {
  decisionConditionForSlot,
  decisionHandleId,
  decisionOutputSlots,
  inferDecisionSlotFromEdge,
  parseDecisionHandleSlot,
  decisionSlotLabel,
} from "@/lib/builder-decision";
import type { BuilderTurn } from "@/lib/builder-types";
import { writeLayoutPositions } from "@/lib/flow-layout-storage";
import type { BuilderNode, BuilderEdge } from "@/lib/flow-translator";
import {
  connectionConditionFormSchema,
  edgeConditionEditFormSchema,
  type ConnectionConditionFormValues,
  type EdgeConditionEditFormValues,
} from "@/lib/schemas/branch-condition";
import type { PushToast } from "../hooks/useBuilderToast";

const nodeTypes: NodeTypes = {
  harnessNode: HarnessNode,
  botNode: BotNode,
  hangupNode: HangupNode,
  waitNode: WaitNode,
  timeRouteNode: TimeRouteNode,
};
const edgeTypes: EdgeTypes = {
  branchingEdge: BranchingEdge,
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export type ClipboardTurn = {
  sourceTurnId: string;
  turn: BuilderTurn;
  sourceNodeData?: {
    isBranchDecision?: boolean;
    branchOutputCount?: number;
    decisionOutputLabels?: Record<string, string>;
  };
  position: { x: number; y: number };
};

/** Imperative handle exposed to parent for keyboard shortcuts */
export interface BuilderCanvasHandle {
  copySelected: () => void;
  pasteClipboard: () => void;
  deleteSelected: () => void;
  quickAddBlock: (kind: BuilderPaletteBlockKind) => void;
}

interface BuilderCanvasProps {
  scenarioId: string | null;
  cacheBucketName?: string | null;
  turnCacheById?: Record<string, { status: "cached" | "skipped" | "failed" | "unknown"; key: string | null }>;
  validationNodeErrors?: NodeStructuralErrors;
  layoutKey: string;
  clipboardTurn: ClipboardTurn | null;
  setClipboardTurn: (t: ClipboardTurn | null) => void;
  onToast: PushToast;
}

export const BuilderCanvas = forwardRef<BuilderCanvasHandle, BuilderCanvasProps>(
  function BuilderCanvas(
    {
      scenarioId,
      cacheBucketName = null,
      turnCacheById = {},
      validationNodeErrors = {},
      layoutKey,
      clipboardTurn,
      setClipboardTurn,
      onToast,
    },
    ref
  ) {
    const reactFlow = useReactFlow<BuilderNode, BuilderEdge>();
    const { resolvedTheme } = useTheme();

    const nodes = useBuilderStore((state) => state.nodes);
    const edges = useBuilderStore((state) => state.edges);
    const updateNodesFromCanvas = useBuilderStore((state) => state.updateNodesFromCanvas);
    const updateEdgesFromCanvas = useBuilderStore((state) => state.updateEdgesFromCanvas);
    const checkpoint = useBuilderStore((state) => state.checkpoint);

    const [pendingConnection, setPendingConnection] = useState<{
      source: string;
      target: string;
    } | null>(null);
    const [pendingEdgeEdit, setPendingEdgeEdit] = useState<{
      edgeId: string;
      source: string;
      target: string;
      currentCondition: string;
    } | null>(null);
    const [connectionError, setConnectionError] = useState<string>("");
    const {
      register: registerConnectionCondition,
      handleSubmit: submitConnectionCondition,
      reset: resetConnectionCondition,
      formState: { errors: connectionConditionErrors },
    } = useForm<ConnectionConditionFormValues>({
      resolver: zodResolver(connectionConditionFormSchema),
      mode: "onChange",
      defaultValues: { condition: "" },
    });
    const {
      register: registerEdgeEditCondition,
      handleSubmit: submitEdgeEditCondition,
      reset: resetEdgeEditCondition,
      formState: { errors: edgeEditConditionErrors },
    } = useForm<EdgeConditionEditFormValues>({
      resolver: zodResolver(edgeConditionEditFormSchema),
      mode: "onChange",
      defaultValues: { condition: "" },
    });

    const nodeStructuralErrors = useMemo(
      () => computeNodeStructuralErrors(nodes, edges),
      [edges, nodes]
    );

    const mergedNodeErrors = useMemo(() => {
      const merged: NodeStructuralErrors = {};
      for (const node of nodes) {
        const structural = nodeStructuralErrors[node.id] ?? [];
        const validation = validationNodeErrors[node.id] ?? [];
        const nextErrors = [...structural];
        for (const message of validation) {
          if (!nextErrors.includes(message)) {
            nextErrors.push(message);
          }
        }
        if (nextErrors.length > 0) {
          merged[node.id] = nextErrors;
        }
      }
      return merged;
    }, [nodeStructuralErrors, nodes, validationNodeErrors]);

    const selectedNode = useMemo(
      () => nodes.find((node) => node.selected) ?? null,
      [nodes]
    );
    const selectedNodeIds = useMemo(
      () => nodes.filter((node) => node.selected).map((node) => node.id),
      [nodes]
    );

    const sourceEdgeCounts = useMemo(() => {
      const counts = new Map<string, number>();
      for (const edge of edges) {
        counts.set(edge.source, (counts.get(edge.source) ?? 0) + 1);
      }
      return counts;
    }, [edges]);

    const handleDecisionSlotLabelChange = useCallback(
      (nodeId: string, slot: string, label: string) => {
        const normalizedSlot = slot.trim().toLowerCase();
        if (!normalizedSlot || normalizedSlot === "default") {
          return;
        }
        const normalizedLabel = label.trim().replace(/\s+/g, " ");
        const condition = normalizedLabel || normalizedSlot;
        const sourceEdges = edges.filter((edge) => edge.source === nodeId);
        const duplicateOnOtherSlots = sourceEdges.some((edge) => {
          const edgeSlot = inferDecisionSlotFromEdge(edge);
          if (edgeSlot === normalizedSlot) {
            return false;
          }
          return edgeCondition(edge).trim().toLowerCase() === condition.toLowerCase();
        });
        if (duplicateOnOtherSlots) {
          onToast(
            `Condition "${condition}" already exists on another output for this decision block.`,
            "warn"
          );
          return;
        }
        checkpoint();
        const nextNodes = nodes.map((node) => {
          if (node.id !== nodeId) {
            return node;
          }
          const currentLabels = isRecord(node.data.decisionOutputLabels)
            ? { ...(node.data.decisionOutputLabels as Record<string, string>) }
            : {};
          if (!normalizedLabel || normalizedLabel === normalizedSlot) {
            delete currentLabels[normalizedSlot];
          } else {
            currentLabels[normalizedSlot] = normalizedLabel;
          }
          return { ...node, data: { ...node.data, decisionOutputLabels: currentLabels } };
        });
        const nextEdges = edges.map((edge) => {
          if (edge.source !== nodeId) {
            return edge;
          }
          const edgeSlot = inferDecisionSlotFromEdge(edge);
          if (edgeSlot !== normalizedSlot) {
            return edge;
          }
          const kind: "branch_default" | "branch_case" =
            condition.toLowerCase() === "default" ? "branch_default" : "branch_case";
          return {
            ...edge,
            label: condition,
            data: { ...(edge.data ?? {}), condition, kind },
          };
        });
        updateNodesFromCanvas(nextNodes);
        updateEdgesFromCanvas(nextEdges);
        setConnectionError("");
      },
      [checkpoint, edges, nodes, onToast, updateEdgesFromCanvas, updateNodesFromCanvas]
    );

    const applyDecisionOutputCount = useCallback(
      (nodeIds: string[], nextRaw: number) => {
        if (nodeIds.length === 0) {
          onToast("Select a decision block first.", "warn");
          return;
        }
        const selectedIds = new Set(nodeIds);
        const targetDecisionNodes = nodes.filter(
          (node) => selectedIds.has(node.id) && node.data.isBranchDecision === true
        );
        if (targetDecisionNodes.length === 0) {
          onToast("No decision block selected.", "warn");
          return;
        }
        const minimumRequired = targetDecisionNodes.reduce((max, node) => {
          const outgoing = edges.filter((edge) => edge.source === node.id).length;
          return Math.max(max, outgoing);
        }, 0);
        const clampedTarget = clampBranchCaseCount(nextRaw);
        const nextCount = Math.max(clampedTarget, minimumRequired);
        const allowedSlots = new Set(decisionOutputSlots(nextCount));
        checkpoint();
        const nextNodes = nodes.map((node) => {
          if (!selectedIds.has(node.id) || node.data.isBranchDecision !== true) {
            return node;
          }
          const currentLabels = isRecord(node.data.decisionOutputLabels)
            ? (node.data.decisionOutputLabels as Record<string, string>)
            : {};
          const prunedLabels: Record<string, string> = {};
          for (const [slot, value] of Object.entries(currentLabels)) {
            if (!allowedSlots.has(slot)) {
              continue;
            }
            const normalized = typeof value === "string" ? value.trim() : "";
            if (!normalized || slot === "default") {
              continue;
            }
            prunedLabels[slot] = normalized;
          }
          return {
            ...node,
            data: {
              ...node.data,
              isBranchDecision: true,
              branchOutputCount: nextCount,
              decisionOutputLabels: prunedLabels,
            },
          };
        });
        updateNodesFromCanvas(nextNodes);
        if (nextCount > clampedTarget) {
          onToast(
            `Outputs cannot be lower than existing connections (${minimumRequired}).`,
            "warn"
          );
        } else {
          onToast(
            `Decision outputs set to ${nextCount} for ${targetDecisionNodes.length} block(s).`,
            "info"
          );
        }
      },
      [checkpoint, edges, nodes, onToast, updateNodesFromCanvas]
    );

    const nodesForCanvas = useMemo(
      () =>
        nodes.map((node) => {
          const mergedDecisionLabels = isRecord(node.data.decisionOutputLabels)
            ? { ...(node.data.decisionOutputLabels as Record<string, string>) }
            : {};
          if (node.data.isBranchDecision === true) {
            const sourceEdges = edges.filter((edge) => edge.source === node.id);
            for (const edge of sourceEdges) {
              const slot = inferDecisionSlotFromEdge(edge);
              if (!slot || slot === "default") {
                continue;
              }
              const condition = edgeCondition(edge).trim();
              if (condition && condition.toLowerCase() !== slot) {
                mergedDecisionLabels[slot] = condition;
              }
            }
          }
          return {
            ...node,
            data: {
              ...node.data,
              decisionOutputLabels: mergedDecisionLabels,
              nodeErrors: mergedNodeErrors[node.id] ?? [],
              scenarioId: scenarioId ?? null,
              turnCacheStatus: turnCacheById[node.id]?.status ?? "unknown",
              turnCacheKey: turnCacheById[node.id]?.key ?? null,
              turnCacheBucketName: cacheBucketName,
              onDecisionOutputCountChange: (nextCount: number) =>
                applyDecisionOutputCount([node.id], nextCount),
              onDecisionSlotLabelChange: (slot: string, label: string) =>
                handleDecisionSlotLabelChange(node.id, slot, label),
              onToast,
            },
          };
        }),
      [
        applyDecisionOutputCount,
        edges,
        handleDecisionSlotLabelChange,
        mergedNodeErrors,
        nodes,
        onToast,
        cacheBucketName,
        scenarioId,
        turnCacheById,
      ]
    );

    const handleRequestEdgeEdit = useCallback(
      (edgeId: string) => {
        const edge = edges.find((item) => item.id === edgeId);
        if (!edge) {
          return;
        }
        const condition = edgeCondition(edge);
        if (condition.toLowerCase() === "default") {
          setConnectionError("Default edge label cannot be edited.");
          onToast("Default edge label cannot be edited.", "warn");
          return;
        }
        setPendingEdgeEdit({
          edgeId,
          source: edge.source,
          target: edge.target,
          currentCondition: condition,
        });
        setPendingConnection(null);
        resetConnectionCondition({ condition: "" });
        resetEdgeEditCondition({ condition });
        setConnectionError("");
      },
      [edges, onToast, resetConnectionCondition, resetEdgeEditCondition]
    );

    const handleRequestEdgeDelete = useCallback(
      (edgeId: string) => {
        checkpoint();
        const result = removeEdgeWithRebalance({ edges, edgeId });
        if (result.error) {
          setConnectionError(result.error);
          onToast(result.error, "warn");
          return;
        }
        updateEdgesFromCanvas(result.edges);
        if (pendingEdgeEdit?.edgeId === edgeId) {
          setPendingEdgeEdit(null);
          resetEdgeEditCondition({ condition: "" });
        }
        setConnectionError("");
      },
      [
        checkpoint,
        edges,
        onToast,
        pendingEdgeEdit?.edgeId,
        resetEdgeEditCondition,
        updateEdgesFromCanvas,
      ]
    );

    const edgesForCanvas = useMemo(
      () =>
        edges.map((edge) => ({
          ...edge,
          type: "branchingEdge",
          data: {
            ...(edge.data ?? {}),
            sourceEdgeCount: sourceEdgeCounts.get(edge.source) ?? 0,
            onRequestEdit: handleRequestEdgeEdit,
            onRequestDelete: handleRequestEdgeDelete,
          },
        })),
      [edges, handleRequestEdgeDelete, handleRequestEdgeEdit, sourceEdgeCounts]
    );

    const onNodesChange = useCallback(
      (changes: NodeChange<BuilderNode>[]) => {
        const nextNodes = applyNodeChanges<BuilderNode>(changes, nodes);
        updateNodesFromCanvas(nextNodes);
        writeLayoutPositions(layoutKey, nextNodes);
      },
      [layoutKey, nodes, updateNodesFromCanvas]
    );

    const onEdgesChange = useCallback(
      (changes: EdgeChange<BuilderEdge>[]) => {
        const nextEdges = applyEdgeChanges<BuilderEdge>(changes, edges);
        updateEdgesFromCanvas(nextEdges);
      },
      [edges, updateEdgesFromCanvas]
    );

    const onConnect = useCallback(
      (connection: Connection) => {
        const source = connection.source;
        const target = connection.target;
        if (!source || !target) {
          return;
        }
        const sourceNode = nodes.find((node) => node.id === source);
        const sourceEdges = edges.filter((edge) => edge.source === source);
        if (sourceNode?.data.isBranchDecision === true) {
          const outputCap = clampBranchCaseCount(
            typeof sourceNode.data.branchOutputCount === "number"
              ? sourceNode.data.branchOutputCount
              : BRANCH_CASE_COUNT_DEFAULT
          );
          const slots = decisionOutputSlots(outputCap);
          const requestedSlot = parseDecisionHandleSlot(connection.sourceHandle);
          let slot = requestedSlot;
          if (!slot) {
            const usedSlots = new Set(
              sourceEdges
                .map((edge) => inferDecisionSlotFromEdge(edge))
                .filter((value): value is string => Boolean(value))
            );
            slot = slots.find((candidate) => !usedSlots.has(candidate)) ?? null;
          }
          if (!slot || !slots.includes(slot)) {
            const message = `This decision block allows ${outputCap} output${
              outputCap === 1 ? "" : "s"
            }. Increase outputs before adding more connections.`;
            setConnectionError(message);
            onToast(message, "warn");
            return;
          }
          const duplicateSlot = sourceEdges.some(
            (edge) => inferDecisionSlotFromEdge(edge) === slot
          );
          if (duplicateSlot) {
            const message = `Output ${decisionSlotLabel(
              slot
            )} is already connected. Remove or rewire that edge first.`;
            setConnectionError(message);
            onToast(message, "warn");
            return;
          }
          checkpoint();
          const userLabels = isRecord(sourceNode.data.decisionOutputLabels)
            ? (sourceNode.data.decisionOutputLabels as Record<string, string>)
            : {};
          const condition = decisionConditionForSlot(slot, userLabels);
          const result = connectWithBranchingRules({
            edges,
            source,
            target,
            condition,
            sourceHandle: decisionHandleId(slot),
            allowDefaultCondition: true,
          });
          if (result.error) {
            setConnectionError(result.error);
            onToast(result.error, "warn");
            return;
          }
          updateEdgesFromCanvas(result.edges);
          return;
        }
        if (shouldPromptForBranchCondition(edges, source)) {
          setPendingEdgeEdit(null);
          resetEdgeEditCondition({ condition: "" });
          setPendingConnection({ source, target });
          resetConnectionCondition({ condition: "" });
          setConnectionError("");
          return;
        }
        checkpoint();
        const result = connectWithBranchingRules({ edges, source, target });
        if (result.error) {
          setConnectionError(result.error);
          onToast(result.error, "warn");
          return;
        }
        updateEdgesFromCanvas(result.edges);
      },
      [
        checkpoint,
        edges,
        nodes,
        onToast,
        resetConnectionCondition,
        resetEdgeEditCondition,
        updateEdgesFromCanvas,
      ]
    );

    const handleConfirmConnection = submitConnectionCondition(
      (values) => {
        if (!pendingConnection) {
          return;
        }
        checkpoint();
        const result = connectWithBranchingRules({
          edges,
          source: pendingConnection.source,
          target: pendingConnection.target,
          condition: values.condition,
        });
        if (result.error) {
          setConnectionError(result.error);
          onToast(result.error, "warn");
          return;
        }
        updateEdgesFromCanvas(result.edges);
        setPendingConnection(null);
        resetConnectionCondition({ condition: "" });
        setConnectionError("");
      },
      (errors) => {
        const message =
          errors.condition?.message ?? "Fix validation errors before adding edge.";
        setConnectionError(message);
        onToast(message, "warn");
      }
    );

    const handleCancelConnection = useCallback(() => {
      setPendingConnection(null);
      resetConnectionCondition({ condition: "" });
      setConnectionError("");
    }, [resetConnectionCondition]);

    const handleCancelEdgeEdit = useCallback(() => {
      setPendingEdgeEdit(null);
      resetEdgeEditCondition({ condition: "" });
      setConnectionError("");
    }, [resetEdgeEditCondition]);

    const handleConfirmEdgeEdit = submitEdgeEditCondition(
      (values) => {
        if (!pendingEdgeEdit) {
          return;
        }
        checkpoint();
        const result = updateEdgeCondition({
          edges,
          edgeId: pendingEdgeEdit.edgeId,
          condition: values.condition,
        });
        if (result.error) {
          setConnectionError(result.error);
          onToast(result.error, "warn");
          return;
        }
        updateEdgesFromCanvas(result.edges);
        setPendingEdgeEdit(null);
        resetEdgeEditCondition({ condition: "" });
        setConnectionError("");
      },
      (errors) => {
        const message =
          errors.condition?.message ?? "Fix validation errors before saving label.";
        setConnectionError(message);
        onToast(message, "warn");
      }
    );

    const handleInsertPaletteBlock = useCallback(
      (kind: BuilderPaletteBlockKind, position: { x: number; y: number }) => {
        checkpoint();
        const result = insertPaletteBlock({
          nodes,
          edges,
          kind,
          position,
          branchCaseCount: kind === "decide_branch" ? BRANCH_CASE_COUNT_DEFAULT : undefined,
        });
        updateNodesFromCanvas(result.nodes);
        updateEdgesFromCanvas(result.edges);
        writeLayoutPositions(layoutKey, result.nodes);
        setConnectionError("");
        onToast(`Added ${kind.replaceAll("_", " ")} block`, "info");
      },
      [checkpoint, edges, layoutKey, nodes, onToast, updateEdgesFromCanvas, updateNodesFromCanvas]
    );

    const handleCanvasDragOver = useCallback((event: ReactDragEvent<HTMLDivElement>) => {
      if (!event.dataTransfer.types.includes(BUILDER_BLOCK_DND_MIME)) {
        return;
      }
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
    }, []);

    const handleCanvasDrop = useCallback(
      (event: ReactDragEvent<HTMLDivElement>) => {
        const raw = event.dataTransfer.getData(BUILDER_BLOCK_DND_MIME);
        if (!raw) {
          return;
        }
        event.preventDefault();
        try {
          const parsed = JSON.parse(raw) as {
            kind?: BuilderPaletteBlockKind;
            branchCaseCount?: number;
          };
          if (
            parsed.kind !== "say_something" &&
            parsed.kind !== "listen_silence" &&
            parsed.kind !== "decide_branch" &&
            parsed.kind !== "hangup_end"
          ) {
            return;
          }
          const position = reactFlow.screenToFlowPosition({
            x: event.clientX,
            y: event.clientY,
          });
          handleInsertPaletteBlock(parsed.kind, position);
        } catch {
          setConnectionError("Invalid block payload dropped on canvas.");
        }
      },
      [handleInsertPaletteBlock, reactFlow]
    );

    const handleCopySelectedBlock = useCallback(() => {
      if (!selectedNode) {
        onToast("Select a block before copying.", "warn");
        return;
      }
      setClipboardTurn({
        sourceTurnId: selectedNode.id,
        turn: { ...selectedNode.data.turn },
        sourceNodeData: {
          isBranchDecision: selectedNode.data.isBranchDecision === true,
          branchOutputCount:
            typeof selectedNode.data.branchOutputCount === "number"
              ? selectedNode.data.branchOutputCount
              : undefined,
          decisionOutputLabels: isRecord(selectedNode.data.decisionOutputLabels)
            ? { ...(selectedNode.data.decisionOutputLabels as Record<string, string>) }
            : undefined,
        },
        position: { ...selectedNode.position },
      });
      onToast(`Copied ${selectedNode.id}`, "info");
    }, [onToast, selectedNode, setClipboardTurn]);

    const handlePasteCopiedBlock = useCallback(() => {
      if (!clipboardTurn) {
        onToast("Clipboard is empty.", "warn");
        return;
      }
      const anchor = selectedNode?.position ?? clipboardTurn.position;
      checkpoint();
      const result = duplicateTurnBlock({
        nodes,
        turn: clipboardTurn.turn,
        sourceTurnId: clipboardTurn.sourceTurnId,
        sourceNodeData: clipboardTurn.sourceNodeData,
        position: { x: anchor.x + 90, y: anchor.y + 90 },
      });
      updateNodesFromCanvas(result.nodes);
      writeLayoutPositions(layoutKey, result.nodes);
      const pastedNode = result.nodes.find((node) => node.id === result.nodeId);
      if (pastedNode) {
        setClipboardTurn({
          sourceTurnId: result.nodeId,
          turn: { ...pastedNode.data.turn },
          sourceNodeData: {
            isBranchDecision: pastedNode.data.isBranchDecision === true,
            branchOutputCount:
              typeof pastedNode.data.branchOutputCount === "number"
                ? pastedNode.data.branchOutputCount
                : undefined,
            decisionOutputLabels: isRecord(pastedNode.data.decisionOutputLabels)
              ? { ...(pastedNode.data.decisionOutputLabels as Record<string, string>) }
              : undefined,
          },
          position: { ...pastedNode.position },
        });
      }
      onToast(`Pasted ${result.nodeId}`, "info");
    }, [
      checkpoint,
      clipboardTurn,
      layoutKey,
      nodes,
      onToast,
      selectedNode,
      setClipboardTurn,
      updateNodesFromCanvas,
    ]);

    const handleDeleteSelectedBlocks = useCallback(() => {
      if (selectedNodeIds.length === 0) {
        onToast("Select a block before deleting.", "warn");
        return;
      }
      const confirmed = window.confirm(
        `Delete ${selectedNodeIds.length} selected block${
          selectedNodeIds.length === 1 ? "" : "s"
        } and connected edges?`
      );
      if (!confirmed) {
        return;
      }
      checkpoint();
      const result = deleteBlocksByNodeIds({ nodes, edges, nodeIds: selectedNodeIds });
      if (result.deletedNodeIds.length === 0) {
        onToast("No selected blocks were removed.", "warn");
        return;
      }
      updateNodesFromCanvas(result.nodes);
      updateEdgesFromCanvas(result.edges);
      writeLayoutPositions(layoutKey, result.nodes);
      if (pendingConnection) {
        const affected =
          result.deletedNodeIds.includes(pendingConnection.source) ||
          result.deletedNodeIds.includes(pendingConnection.target);
        if (affected) {
          setPendingConnection(null);
          resetConnectionCondition({ condition: "" });
        }
      }
      if (pendingEdgeEdit) {
        const edgeStillExists = result.edges.some((edge) => edge.id === pendingEdgeEdit.edgeId);
        if (!edgeStillExists) {
          setPendingEdgeEdit(null);
          resetEdgeEditCondition({ condition: "" });
        }
      }
      onToast(`Deleted ${result.deletedNodeIds.length} block(s)`, "info");
    }, [
      checkpoint,
      edges,
      layoutKey,
      nodes,
      onToast,
      pendingConnection,
      pendingEdgeEdit,
      resetConnectionCondition,
      resetEdgeEditCondition,
      selectedNodeIds,
      updateEdgesFromCanvas,
      updateNodesFromCanvas,
    ]);

    const handleQuickAddBlock = useCallback(
      (kind: BuilderPaletteBlockKind) => {
        const flowPane = document.querySelector(".react-flow");
        if (flowPane instanceof HTMLElement) {
          const rect = flowPane.getBoundingClientRect();
          const center = reactFlow.screenToFlowPosition({
            x: rect.left + rect.width / 2,
            y: rect.top + rect.height / 2,
          });
          handleInsertPaletteBlock(kind, center);
          return;
        }
        handleInsertPaletteBlock(kind, { x: 240, y: 240 });
      },
      [handleInsertPaletteBlock, reactFlow]
    );

    // Expose imperative handles to parent for keyboard shortcuts + palette
    useImperativeHandle(
      ref,
      () => ({
        copySelected: handleCopySelectedBlock,
        pasteClipboard: handlePasteCopiedBlock,
        deleteSelected: handleDeleteSelectedBlocks,
        quickAddBlock: handleQuickAddBlock,
      }),
      [handleCopySelectedBlock, handleDeleteSelectedBlocks, handlePasteCopiedBlock, handleQuickAddBlock]
    );

    return (
      <div className="relative h-full min-h-[520px] rounded-lg border border-border bg-bg-surface">
        <ReactFlow<BuilderNode, BuilderEdge>
          nodes={nodesForCanvas}
          edges={edgesForCanvas}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onDragOver={handleCanvasDragOver}
          onDrop={handleCanvasDrop}
          onNodeDragStart={checkpoint}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          colorMode={resolvedTheme === "light" ? "light" : "dark"}
          fitView
          style={{ background: "rgb(var(--bg-base))" }}
        >
          <Background
            id="builder-grid"
            variant={BackgroundVariant.Dots}
            gap={18}
            size={1.3}
            color="rgb(var(--flow-grid))"
            bgColor="rgb(var(--bg-base))"
          />
          <Background
            id="builder-grid-strong"
            variant={BackgroundVariant.Dots}
            gap={90}
            size={1.8}
            color="rgb(var(--flow-grid-strong))"
            bgColor="transparent"
          />
          <Controls className="!rounded-xl" />
        </ReactFlow>

        {pendingConnection && (
          <div className="absolute left-3 top-3 z-20 w-[420px] max-w-[calc(100%-1.5rem)] rounded-md border border-border bg-bg-surface p-3 shadow-md">
            <p className="text-sm font-medium text-text-primary">Add branch condition</p>
            <p className="mt-1 text-xs text-text-secondary">
              Source: <span className="font-mono">{pendingConnection.source}</span> → Target:{" "}
              <span className="font-mono">{pendingConnection.target}</span>
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <input
                {...registerConnectionCondition("condition")}
                data-testid="branch-condition-input"
                placeholder="e.g. billing support (blank = auto path_n)"
                className="min-w-[220px] flex-1 rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-primary focus:border-border-focus focus:outline-none"
              />
              <Button variant="secondary" size="sm" onClick={handleCancelConnection}>
                Cancel
              </Button>
              <Button
                data-testid="branch-condition-add-btn"
                size="sm"
                onClick={() => void handleConfirmConnection()}
              >
                Add Edge
              </Button>
            </div>
            {connectionConditionErrors.condition?.message ? (
              <p data-testid="branch-condition-inline-error" className="mt-2 text-xs text-fail">
                {connectionConditionErrors.condition.message}
              </p>
            ) : null}
          </div>
        )}

        {pendingEdgeEdit && (
          <div className="absolute left-3 top-3 z-20 w-[420px] max-w-[calc(100%-1.5rem)] rounded-md border border-border bg-bg-surface p-3 shadow-md">
            <p className="text-sm font-medium text-text-primary">Edit edge condition</p>
            <p className="mt-1 text-xs text-text-secondary">
              Source: <span className="font-mono">{pendingEdgeEdit.source}</span> → Target:{" "}
              <span className="font-mono">{pendingEdgeEdit.target}</span>
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <input
                {...registerEdgeEditCondition("condition")}
                data-testid="edge-condition-edit-input"
                placeholder="Condition label"
                className="min-w-[220px] flex-1 rounded-md border border-border bg-bg-elevated px-3 py-2 text-xs text-text-primary focus:border-border-focus focus:outline-none"
              />
              <Button variant="secondary" size="sm" onClick={handleCancelEdgeEdit}>
                Cancel
              </Button>
              <Button
                data-testid="edge-condition-save-btn"
                size="sm"
                onClick={() => void handleConfirmEdgeEdit()}
              >
                Save Label
              </Button>
            </div>
            {edgeEditConditionErrors.condition?.message ? (
              <p data-testid="edge-condition-inline-error" className="mt-2 text-xs text-fail">
                {edgeEditConditionErrors.condition.message}
              </p>
            ) : null}
          </div>
        )}

        {connectionError && (
          <div className="absolute bottom-3 left-3 z-20 rounded-md border border-warn-border bg-warn-bg px-3 py-2 text-xs text-warn">
            {connectionError}
          </div>
        )}
      </div>
    );
  }
);
