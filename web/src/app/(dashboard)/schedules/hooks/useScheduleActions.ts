"use client";

import { useState } from "react";
import {
  createSchedule,
  deleteSchedule,
  patchSchedule,
  type ScheduleCreateRequest,
  type SchedulePatchRequest,
} from "@/lib/api";

export function useScheduleActions(mutate: () => Promise<unknown>) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState("");

  const createOne = async (payload: ScheduleCreateRequest) => {
    setActionError("");
    await createSchedule(payload);
    await mutate();
  };

  const updateOne = async (scheduleId: string, payload: SchedulePatchRequest) => {
    setActionError("");
    await patchSchedule(scheduleId, payload);
    await mutate();
  };

  const toggleActive = async (scheduleId: string, nextActive: boolean) => {
    setBusyId(scheduleId);
    setActionError("");
    try {
      await patchSchedule(scheduleId, { active: nextActive });
      await mutate();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to update schedule");
    } finally {
      setBusyId(null);
    }
  };

  const removeSchedule = async (scheduleId: string) => {
    if (!window.confirm("Delete this schedule?")) {
      return;
    }
    setBusyId(scheduleId);
    setActionError("");
    try {
      await deleteSchedule(scheduleId);
      await mutate();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to delete schedule");
    } finally {
      setBusyId(null);
    }
  };

  return {
    busyId,
    actionError,
    setActionError,
    createOne,
    updateOne,
    toggleActive,
    removeSchedule,
  };
}
