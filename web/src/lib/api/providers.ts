import useSWR from "swr";

import { fetcher } from "./fetcher";
import type {
    ProviderAvailableListResponse,
    ProviderAvailabilitySummaryResponse,
    TenantProviderQuotaListResponse,
    TenantProviderUsageListResponse,
} from "./types";

export function useAvailableProviders(enabled = true) {
  return useSWR<ProviderAvailableListResponse>(
    enabled ? "/providers/available" : null,
    fetcher,
    {
      refreshInterval: 60_000,
    }
  );
}

export function availableProviderItems(
  response: ProviderAvailableListResponse | undefined
): ProviderAvailabilitySummaryResponse[] {
  return response?.items ?? [];
}

export function useTenantProviderUsage(enabled = true) {
  return useSWR<TenantProviderUsageListResponse>(
    enabled ? "/tenants/me/providers/usage" : null,
    fetcher,
    {
      refreshInterval: 60_000,
    }
  );
}

export function useTenantProviderQuota(enabled = true) {
  return useSWR<TenantProviderQuotaListResponse>(
    enabled ? "/tenants/me/providers/quota" : null,
    fetcher,
    {
      refreshInterval: 60_000,
    }
  );
}
