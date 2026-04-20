import useSWR from "swr";
import { buildApiUrl, fetcher } from "./fetcher";
import type { AuditEvent, AuditFilters } from "./types";

export function useAuditEvents(filters: AuditFilters) {
  const path = buildApiUrl("/audit/", {
    action: filters.action,
    resource_type: filters.resourceType,
    actor_id: filters.actorId,
    from_ts: filters.fromTs,
    to_ts: filters.toTs,
    limit: filters.limit ?? 200,
  });
  return useSWR<AuditEvent[]>(path, fetcher, {
    refreshInterval: 10000,
  });
}
