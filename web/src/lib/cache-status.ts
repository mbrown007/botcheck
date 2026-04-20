export function cacheStatusVariant(status?: string | null): string {
  const normalized = (status ?? "cold").toLowerCase();
  if (normalized === "warm") return "pass";
  if (normalized === "warming" || normalized === "partial") return "warn";
  return "pending";
}
