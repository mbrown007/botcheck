import useSWR from "swr";
import { apiFetch, buildApiUrl, fetcher } from "./fetcher";
import type {
  AdminAuditEventsListResponse,
  AdminSIPSyncResponse,
  AdminSIPTrunkPoolAssignmentCreateRequest,
  AdminSIPTrunkPoolAssignmentPatchRequest,
  AdminSIPTrunkPoolCreateRequest,
  AdminSIPTrunkPoolDetailResponse,
  AdminSIPTrunkPoolMemberCreateRequest,
  AdminSIPTrunkPoolPatchRequest,
  AdminSIPTrunkPoolsListResponse,
  AdminSIPTrunksListResponse,
  AdminProviderAssignmentsListResponse,
  AdminProviderAssignRequest,
  AdminProviderCredentialMutationResponse,
  AdminProviderCredentialWriteRequest,
  AdminProviderCreateRequest,
  AdminProviderDeleteResponse,
  AdminProviderQuotaResponse,
  AdminProviderQuotaPoliciesListResponse,
  AdminProviderQuotaPolicyMutationResponse,
  AdminProviderQuotaPolicyResponse,
  AdminProviderQuotaPolicyWriteRequest,
  AdminProvidersListResponse,
  AdminProviderSummaryResponse,
  AdminProviderUpdateRequest,
  AdminProviderUsageResponse,
  AdminSystemConfigResponse,
  AdminSystemHealthResponse,
  AdminSystemQuotaPatchRequest,
  AdminSystemQuotaResponse,
  AdminTenantActionResponse,
  AdminTenantProviderAssignmentMutationResponse,
  AdminTenantProviderAssignRequest,
  AdminTenantCreateRequest,
  AdminTenantDetailResponse,
  AdminTenantPatchRequest,
  AdminTenantsListResponse,
  AdminUserActionResponse,
  AdminUserCreateRequest,
  AdminUserDetailResponse,
  AdminUserPasswordResetRequest,
  AdminUserReset2FAResponse,
  AdminUsersListResponse,
} from "./types";

async function adminRequest<T>(path: string, body?: unknown, method = "POST"): Promise<T> {
  return apiFetch<T>(path, {
    method,
    json: body,
  });
}

export function useAdminUsers(limit = 50, offset = 0) {
  return useSWR<AdminUsersListResponse>(buildApiUrl("/admin/users/", { limit, offset }), fetcher);
}

export function useAdminTenants(limit = 50, offset = 0, enabled = true) {
  return useSWR<AdminTenantsListResponse>(
    enabled ? buildApiUrl("/admin/tenants/", { limit, offset }) : null,
    fetcher
  );
}

export function useAdminAudit(
  params: {
    tenantId?: string;
    actorId?: string;
    action?: string;
    resourceType?: string;
    fromTs?: string;
    toTs?: string;
    limit?: number;
    offset?: number;
  } = {},
  enabled = true
) {
  return useSWR<AdminAuditEventsListResponse>(
    enabled
      ? buildApiUrl("/admin/audit/", {
          tenant_id: params.tenantId,
          actor_id: params.actorId,
          action: params.action,
          resource_type: params.resourceType,
          from_ts: params.fromTs,
          to_ts: params.toTs,
          limit: params.limit ?? 100,
          offset: params.offset ?? 0,
        })
      : null,
    fetcher
  );
}

export function useAdminSipTrunks(enabled = true) {
  return useSWR<AdminSIPTrunksListResponse>(enabled ? "/admin/sip/trunks" : null, fetcher);
}

export function useAdminSipPools(enabled = true) {
  return useSWR<AdminSIPTrunkPoolsListResponse>(enabled ? "/admin/sip/pools" : null, fetcher);
}

export function useAdminSystemHealth(enabled = true) {
  return useSWR<AdminSystemHealthResponse>(enabled ? "/admin/system/health" : null, fetcher);
}

export function useAdminSystemConfig(enabled = true) {
  return useSWR<AdminSystemConfigResponse>(enabled ? "/admin/system/config" : null, fetcher);
}

export function useAdminSystemQuotas(enabled = true) {
  return useSWR<AdminSystemQuotaResponse>(enabled ? "/admin/system/quotas" : null, fetcher);
}

export function useAdminProviders(enabled = true) {
  return useSWR<AdminProvidersListResponse>(enabled ? "/admin/providers/" : null, fetcher);
}

export function useAdminProviderAssignments(providerId: string | null | undefined, enabled = true) {
  const path = providerId ? `/admin/providers/${encodeURIComponent(providerId)}/assignments` : null;
  return useSWR<AdminProviderAssignmentsListResponse>(enabled && path ? path : null, fetcher);
}

export function useAdminProviderQuotaPolicies(providerId: string | null | undefined, enabled = true) {
  const path = providerId ? `/admin/providers/${encodeURIComponent(providerId)}/quota-policies` : null;
  return useSWR<AdminProviderQuotaPoliciesListResponse>(enabled && path ? path : null, fetcher);
}

export function useAdminProviderUsage(providerId: string | null | undefined, enabled = true) {
  const path = providerId ? `/admin/providers/${encodeURIComponent(providerId)}/usage` : null;
  return useSWR<AdminProviderUsageResponse>(enabled && path ? path : null, fetcher);
}

export function useAdminProviderQuota(providerId: string | null | undefined, enabled = true) {
  const path = providerId ? `/admin/providers/${encodeURIComponent(providerId)}/quota` : null;
  return useSWR<AdminProviderQuotaResponse>(enabled && path ? path : null, fetcher);
}

export async function createAdminUser(payload: AdminUserCreateRequest) {
  return adminRequest<AdminUserDetailResponse>("/admin/users/", payload);
}

export async function lockAdminUser(userId: string) {
  return adminRequest<AdminUserActionResponse>(`/admin/users/${encodeURIComponent(userId)}/lock`);
}

export async function unlockAdminUser(userId: string) {
  return adminRequest<AdminUserActionResponse>(`/admin/users/${encodeURIComponent(userId)}/unlock`);
}

export async function resetAdminUserPassword(
  userId: string,
  payload: AdminUserPasswordResetRequest
) {
  return adminRequest<AdminUserActionResponse>(
    `/admin/users/${encodeURIComponent(userId)}/reset-password`,
    payload
  );
}

export async function resetAdminUser2FA(userId: string) {
  return adminRequest<AdminUserReset2FAResponse>(`/admin/users/${encodeURIComponent(userId)}/reset-2fa`);
}

export async function revokeAdminUserSessions(userId: string) {
  return adminRequest<AdminUserActionResponse>(
    `/admin/users/${encodeURIComponent(userId)}/sessions`,
    undefined,
    "DELETE"
  );
}

export async function createAdminTenant(payload: AdminTenantCreateRequest) {
  return adminRequest<AdminTenantDetailResponse>("/admin/tenants/", payload);
}

export async function updateAdminTenant(
  tenantId: string,
  payload: AdminTenantPatchRequest
) {
  return adminRequest<AdminTenantDetailResponse>(
    `/admin/tenants/${encodeURIComponent(tenantId)}`,
    payload,
    "PATCH"
  );
}

export async function createAdminProvider(payload: AdminProviderCreateRequest) {
  return adminRequest<AdminProviderSummaryResponse>("/admin/providers/", payload);
}

export async function updateAdminProvider(
  providerId: string,
  payload: AdminProviderUpdateRequest
) {
  return adminRequest<AdminProviderSummaryResponse>(
    `/admin/providers/${encodeURIComponent(providerId)}`,
    payload,
    "PATCH"
  );
}

export async function deleteAdminProvider(providerId: string) {
  return adminRequest<AdminProviderDeleteResponse>(
    `/admin/providers/${encodeURIComponent(providerId)}`,
    undefined,
    "DELETE"
  );
}

export async function assignAdminProvider(providerId: string, payload: AdminProviderAssignRequest) {
  return adminRequest<AdminProviderSummaryResponse>(
    `/admin/providers/${encodeURIComponent(providerId)}/assign`,
    payload
  );
}

export async function deleteAdminProviderAssignment(providerId: string) {
  return adminRequest<AdminProviderSummaryResponse>(
    `/admin/providers/${encodeURIComponent(providerId)}/assign`,
    undefined,
    "DELETE"
  );
}

export async function upsertAdminProviderCredential(
  providerId: string,
  payload: AdminProviderCredentialWriteRequest
) {
  return adminRequest<AdminProviderCredentialMutationResponse>(
    `/admin/providers/${encodeURIComponent(providerId)}/credentials`,
    payload
  );
}

export async function deleteAdminProviderCredential(providerId: string) {
  return adminRequest<AdminProviderCredentialMutationResponse>(
    `/admin/providers/${encodeURIComponent(providerId)}/credentials`,
    undefined,
    "DELETE"
  );
}

export async function upsertAdminProviderQuotaPolicy(
  providerId: string,
  payload: AdminProviderQuotaPolicyWriteRequest
) {
  return adminRequest<AdminProviderQuotaPolicyResponse>(
    `/admin/providers/${encodeURIComponent(providerId)}/quota-policies`,
    payload
  );
}

export async function deleteAdminProviderQuotaPolicy(
  providerId: string,
  tenantId: string,
  metric: string
) {
  return adminRequest<AdminProviderQuotaPolicyMutationResponse>(
    `/admin/providers/${encodeURIComponent(providerId)}/quota-policies/${encodeURIComponent(tenantId)}/${encodeURIComponent(metric)}`,
    undefined,
    "DELETE"
  );
}

export async function assignAdminTenantProvider(
  tenantId: string,
  payload: AdminTenantProviderAssignRequest
) {
  return adminRequest<AdminTenantProviderAssignmentMutationResponse>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/providers/assign`,
    payload
  );
}

export async function deleteAdminTenantProviderAssignment(tenantId: string, providerId: string) {
  return adminRequest<AdminTenantProviderAssignmentMutationResponse>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/providers/${encodeURIComponent(providerId)}/assign`,
    undefined,
    "DELETE"
  );
}

export async function suspendAdminTenant(tenantId: string) {
  return adminRequest<AdminTenantActionResponse>(`/admin/tenants/${encodeURIComponent(tenantId)}/suspend`);
}

export async function reinstateAdminTenant(tenantId: string) {
  return adminRequest<AdminTenantActionResponse>(
    `/admin/tenants/${encodeURIComponent(tenantId)}/reinstate`
  );
}

export async function deleteAdminTenant(tenantId: string) {
  return adminRequest<AdminTenantActionResponse>(
    `/admin/tenants/${encodeURIComponent(tenantId)}`,
    undefined,
    "DELETE"
  );
}

export async function syncAdminSipTrunks() {
  return adminRequest<AdminSIPSyncResponse>("/admin/sip/trunks/sync");
}

export async function createAdminSipPool(payload: AdminSIPTrunkPoolCreateRequest) {
  return adminRequest<AdminSIPTrunkPoolDetailResponse>("/admin/sip/pools", payload);
}

export async function patchAdminSipPool(
  trunkPoolId: string,
  payload: AdminSIPTrunkPoolPatchRequest
) {
  return adminRequest<AdminSIPTrunkPoolDetailResponse>(
    `/admin/sip/pools/${encodeURIComponent(trunkPoolId)}`,
    payload,
    "PATCH"
  );
}

export async function addAdminSipPoolMember(
  trunkPoolId: string,
  payload: AdminSIPTrunkPoolMemberCreateRequest
) {
  return adminRequest<AdminSIPTrunkPoolDetailResponse>(
    `/admin/sip/pools/${encodeURIComponent(trunkPoolId)}/members`,
    payload
  );
}

export async function removeAdminSipPoolMember(trunkPoolId: string, trunkId: string) {
  return adminRequest<AdminSIPTrunkPoolDetailResponse>(
    `/admin/sip/pools/${encodeURIComponent(trunkPoolId)}/members/${encodeURIComponent(trunkId)}`,
    undefined,
    "DELETE"
  );
}

export async function assignAdminSipPool(
  trunkPoolId: string,
  payload: AdminSIPTrunkPoolAssignmentCreateRequest
) {
  return adminRequest<AdminSIPTrunkPoolDetailResponse>(
    `/admin/sip/pools/${encodeURIComponent(trunkPoolId)}/assign`,
    payload
  );
}

export async function patchAdminSipPoolAssignment(
  trunkPoolId: string,
  tenantId: string,
  payload: AdminSIPTrunkPoolAssignmentPatchRequest
) {
  return adminRequest<AdminSIPTrunkPoolDetailResponse>(
    `/admin/sip/pools/${encodeURIComponent(trunkPoolId)}/assign/${encodeURIComponent(tenantId)}`,
    payload,
    "PATCH"
  );
}

export async function revokeAdminSipPool(trunkPoolId: string, tenantId: string) {
  return adminRequest<AdminSIPTrunkPoolDetailResponse>(
    `/admin/sip/pools/${encodeURIComponent(trunkPoolId)}/assign/${encodeURIComponent(tenantId)}`,
    undefined,
    "DELETE"
  );
}

export async function patchAdminSystemQuotas(payload: AdminSystemQuotaPatchRequest) {
  return adminRequest<AdminSystemQuotaResponse>("/admin/system/quotas", payload, "PATCH");
}
