import useSWR from "swr";

import { apiFetch, fetcher } from "./fetcher";
import type {
  BotDestinationDetail,
  BotDestinationSummary,
  BotDestinationUpsertRequest,
  TenantSIPPoolsListResponse,
  TenantSIPPoolPatchRequest,
  TenantSIPPoolResponse,
} from "./types";

export function useTransportProfiles(enabled = true) {
  return useSWR<BotDestinationSummary[]>(enabled ? "/destinations/" : null, fetcher);
}

export function useTenantSIPPools(enabled = true) {
  return useSWR<TenantSIPPoolsListResponse>(enabled ? "/sip/pools" : null, fetcher);
}

export async function fetchTransportProfileDetail(
  destinationId: string,
): Promise<BotDestinationDetail> {
  return apiFetch<BotDestinationDetail>(`/destinations/${destinationId}`, {
    context: "Fetch transport profile detail failed",
  });
}

export async function createTransportProfile(
  body: BotDestinationUpsertRequest,
): Promise<BotDestinationDetail> {
  return apiFetch<BotDestinationDetail>("/destinations/", {
    method: "POST",
    json: body,
    context: "Create transport profile failed",
  });
}

export async function updateTransportProfile(
  destinationId: string,
  body: BotDestinationUpsertRequest,
): Promise<BotDestinationDetail> {
  return apiFetch<BotDestinationDetail>(`/destinations/${destinationId}`, {
    method: "PUT",
    json: body,
    context: "Update transport profile failed",
  });
}

export async function deleteTransportProfile(destinationId: string): Promise<void> {
  await apiFetch<void>(`/destinations/${destinationId}`, {
    method: "DELETE",
    context: "Delete transport profile failed",
  });
}

export async function patchTenantSIPPool(
  trunkPoolId: string,
  body: TenantSIPPoolPatchRequest,
): Promise<TenantSIPPoolResponse> {
  return apiFetch<TenantSIPPoolResponse>(`/sip/pools/${trunkPoolId}`, {
    method: "PATCH",
    json: body,
    context: "Update tenant SIP pool failed",
  });
}
