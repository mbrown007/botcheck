export type ScheduleTimelineView = "24h" | "7d" | "30d";

export interface ScheduleTimelineSlot {
  startMs: number;
  endMs: number;
  label: string;
  shortLabel: string;
}

export interface ScheduleTimelineSummary {
  slots: ScheduleTimelineSlot[];
  previewCount: number;
}

function startOfHour(date: Date): Date {
  const next = new Date(date);
  next.setMinutes(0, 0, 0);
  return next;
}

function startOfDay(date: Date): Date {
  const next = new Date(date);
  next.setHours(0, 0, 0, 0);
  return next;
}

export function buildScheduleTimeline(view: ScheduleTimelineView, now = new Date()): ScheduleTimelineSummary {
  if (view === "24h") {
    const anchor = startOfHour(now);
    const slots = Array.from({ length: 24 }, (_, index) => {
      const start = new Date(anchor);
      start.setHours(anchor.getHours() + index);
      const end = new Date(start);
      end.setHours(start.getHours() + 1);
      return {
        startMs: start.getTime(),
        endMs: end.getTime(),
        label: start.toLocaleString(undefined, { hour: "numeric", minute: "2-digit" }),
        shortLabel: start.toLocaleString(undefined, { hour: "numeric" }),
      };
    });
    return { slots, previewCount: 96 };
  }

  const dayCount = view === "7d" ? 7 : 30;
  const anchor = startOfDay(now);
  const slots = Array.from({ length: dayCount }, (_, index) => {
    const start = new Date(anchor);
    start.setDate(anchor.getDate() + index);
    const end = new Date(start);
    end.setDate(start.getDate() + 1);
    return {
      startMs: start.getTime(),
      endMs: end.getTime(),
      label: start.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }),
      shortLabel:
        view === "7d"
          ? start.toLocaleDateString(undefined, { weekday: "short" })
          : start.toLocaleDateString(undefined, { month: "numeric", day: "numeric" }),
    };
  });
  return {
    slots,
    previewCount: view === "7d" ? 168 : 240,
  };
}

export function bucketScheduleOccurrences(
  occurrences: string[],
  slots: ScheduleTimelineSlot[],
): number[] {
  const counts = Array.from({ length: slots.length }, () => 0);
  for (const occurrence of occurrences) {
    const ts = new Date(occurrence).getTime();
    const slotIndex = slots.findIndex((slot) => ts >= slot.startMs && ts < slot.endMs);
    if (slotIndex >= 0) {
      counts[slotIndex] += 1;
    }
  }
  return counts;
}
