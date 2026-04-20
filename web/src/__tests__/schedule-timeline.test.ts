import assert from "node:assert/strict";
import test from "node:test";
import { buildScheduleTimeline, bucketScheduleOccurrences } from "@/lib/schedule-timeline";

test("buildScheduleTimeline returns 24 hourly slots for 24h view", () => {
  const summary = buildScheduleTimeline("24h", new Date("2026-03-14T10:23:00Z"));
  assert.equal(summary.slots.length, 24);
  assert.equal(summary.previewCount, 96);
  assert.equal(summary.slots[0]?.shortLabel.length > 0, true);
});

test("buildScheduleTimeline returns daily slots for week and month views", () => {
  const week = buildScheduleTimeline("7d", new Date("2026-03-14T10:23:00Z"));
  const month = buildScheduleTimeline("30d", new Date("2026-03-14T10:23:00Z"));
  assert.equal(week.slots.length, 7);
  assert.equal(month.slots.length, 30);
});

test("bucketScheduleOccurrences counts occurrences into slot windows", () => {
  const { slots } = buildScheduleTimeline("24h", new Date("2026-03-14T10:23:00Z"));
  const counts = bucketScheduleOccurrences(
    [
      new Date(slots[0]!.startMs + 5 * 60 * 1000).toISOString(),
      new Date(slots[0]!.startMs + 25 * 60 * 1000).toISOString(),
      new Date(slots[1]!.startMs + 15 * 60 * 1000).toISOString(),
    ],
    slots,
  );
  assert.equal(counts[0], 2);
  assert.equal(counts[1], 1);
  assert.equal(counts.slice(2).every((count) => count === 0), true);
});
