"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import type { AIScenarioRecord } from "@/lib/api/types";
import {
  aiScenarioRecordEditorFormSchema,
  createEmptyAIScenarioRecordEditorValues,
  type AIScenarioRecordEditorFormValues,
} from "@/lib/schemas/ai-scenario-editor";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";

interface AIScenarioRecordsCardProps {
  selectedAIScenarioId: string;
  selectedScenarioName: string;
  creatingRecord: boolean;
  deletingRecordId: string | null;
  selectedRecords: AIScenarioRecord[] | undefined;
  selectedRecordsError?: Error;
  onCreateRecord: (values: AIScenarioRecordEditorFormValues) => Promise<boolean> | boolean;
  onDeleteRecord: (recordId: string) => void;
}

export function AIScenarioRecordsCard({
  selectedAIScenarioId,
  selectedScenarioName,
  creatingRecord,
  deletingRecordId,
  selectedRecords,
  selectedRecordsError,
  onCreateRecord,
  onDeleteRecord,
}: AIScenarioRecordsCardProps) {
  const form = useForm<AIScenarioRecordEditorFormValues>({
    resolver: zodResolver(aiScenarioRecordEditorFormSchema),
    mode: "onChange",
    defaultValues: createEmptyAIScenarioRecordEditorValues(),
  });
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = form;

  async function onSubmit(values: AIScenarioRecordEditorFormValues) {
    const created = await onCreateRecord(values);
    if (created) {
      reset(createEmptyAIScenarioRecordEditorValues());
    }
  }

  return (
    <Card>
      <CardHeader>
        <span className="text-sm font-medium text-text-secondary">
          Dataset Records · {selectedScenarioName || selectedAIScenarioId}
        </span>
      </CardHeader>
      <CardBody className="space-y-3">
        <p className="text-xs text-text-muted">
          Optional regression variants for this AI scenario. Leave empty if you want pure
          intent-first role-play without dataset seeding.
        </p>
        <div className="grid gap-2 lg:grid-cols-[120px_1fr_1fr_auto]">
          <div className="space-y-1">
            <input
              data-testid="ai-record-order-input"
              {...register("orderIndex")}
              placeholder="Order"
              className="w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-sm text-text-primary focus:border-border-focus focus:outline-none"
            />
            {errors.orderIndex ? (
              <p className="text-xs text-fail">{errors.orderIndex.message}</p>
            ) : null}
          </div>
          <div className="space-y-1">
            <textarea
              data-testid="ai-record-input-text"
              {...register("inputText")}
              rows={2}
              placeholder="Input text"
              className="w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-sm text-text-primary focus:border-border-focus focus:outline-none"
            />
            {errors.inputText ? <p className="text-xs text-fail">{errors.inputText.message}</p> : null}
          </div>
          <div className="space-y-1">
            <textarea
              data-testid="ai-record-expected-output"
              {...register("expectedOutput")}
              rows={2}
              placeholder="Expected output"
              className="w-full rounded-md border border-border bg-bg-base px-2 py-1.5 text-sm text-text-primary focus:border-border-focus focus:outline-none"
            />
            {errors.expectedOutput ? (
              <p className="text-xs text-fail">{errors.expectedOutput.message}</p>
            ) : null}
          </div>
          <div className="flex items-start justify-end">
            <Button
              data-testid="ai-record-create-btn"
              size="sm"
              onClick={handleSubmit(onSubmit)}
              disabled={creatingRecord}
            >
              {creatingRecord ? "Adding…" : "Add Record"}
            </Button>
          </div>
        </div>

        {selectedRecordsError ? (
          <p className="text-sm text-fail">Failed to load records: {selectedRecordsError.message}</p>
        ) : !selectedRecords ? (
          <p className="text-sm text-text-muted">Loading records…</p>
        ) : selectedRecords.length === 0 ? (
          <p className="text-sm text-text-muted">No records for this scenario.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-text-muted text-xs uppercase tracking-wide">
                <th className="px-3 py-2 text-left font-medium">Order</th>
                <th className="px-3 py-2 text-left font-medium">Input</th>
                <th className="px-3 py-2 text-left font-medium">Expected Output</th>
                <th className="px-3 py-2 text-left font-medium">Active</th>
                <th className="px-3 py-2 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {selectedRecords.map((record) => (
                <tr key={record.record_id} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 font-mono text-xs text-text-secondary">{record.order_index}</td>
                  <td className="px-3 py-2 text-xs text-text-secondary">{record.input_text}</td>
                  <td className="px-3 py-2 text-xs text-text-secondary">{record.expected_output}</td>
                  <td className="px-3 py-2">
                    <StatusBadge
                      value={record.is_active ? "pass" : "pending"}
                      label={record.is_active ? "active" : "inactive"}
                    />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Button
                      data-testid={`ai-record-delete-${record.record_id}`}
                      size="sm"
                      variant="secondary"
                      onClick={() => onDeleteRecord(record.record_id)}
                      disabled={deletingRecordId === record.record_id}
                    >
                      {deletingRecordId === record.record_id ? "Deleting…" : "Delete"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardBody>
    </Card>
  );
}
