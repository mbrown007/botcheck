import useSWR from "swr";
import { apiFetch, fetcher } from "./fetcher";
import type {
  CurrentUserResponse,
  TotpStatusResponse,
  AuthLoginRequest,
  AuthLoginResponse,
  AuthTotpLoginRequest,
  TotpEnrollmentStartResponse,
  TotpEnrollmentConfirmRequest,
  TotpEnrollmentConfirmResponse,
  TotpRecoveryCodesRegenerateResponse,
  LogoutAllResponse,
} from "./types";

export function useCurrentUser() {
  return useSWR<CurrentUserResponse>("/auth/me", fetcher);
}

export async function fetchCurrentUser(tokenOverride?: string): Promise<CurrentUserResponse> {
  return apiFetch<CurrentUserResponse>("/auth/me", {
    headers: tokenOverride ? { Authorization: `Bearer ${tokenOverride}` } : undefined,
    includeAuth: !tokenOverride,
    clearOn401: false,
    context: "Current user lookup failed",
  });
}

export function useTotpStatus() {
  return useSWR<TotpStatusResponse>("/auth/totp/status", fetcher);
}

export async function login(
  payload: AuthLoginRequest
): Promise<AuthLoginResponse> {
  return apiFetch<AuthLoginResponse>("/auth/login", {
    method: "POST",
    json: payload,
    includeAuth: false,
    clearOn401: false,
    context: "Login failed",
  });
}

export async function loginWithTotp(
  payload: AuthTotpLoginRequest
): Promise<AuthLoginResponse> {
  return apiFetch<AuthLoginResponse>("/auth/login/totp", {
    method: "POST",
    json: payload,
    includeAuth: false,
    clearOn401: false,
    context: "TOTP login failed",
  });
}

export async function startTotpEnrollment(): Promise<TotpEnrollmentStartResponse> {
  return apiFetch<TotpEnrollmentStartResponse>("/auth/totp/enroll/start", {
    method: "POST",
    context: "Start TOTP enrollment failed",
  });
}

export async function confirmTotpEnrollment(
  payload: TotpEnrollmentConfirmRequest
): Promise<TotpEnrollmentConfirmResponse> {
  return apiFetch<TotpEnrollmentConfirmResponse>("/auth/totp/enroll/confirm", {
    method: "POST",
    json: payload,
    context: "Confirm TOTP enrollment failed",
  });
}

export async function regenerateTotpRecoveryCodes(): Promise<TotpRecoveryCodesRegenerateResponse> {
  return apiFetch<TotpRecoveryCodesRegenerateResponse>("/auth/totp/recovery-codes/regenerate", {
    method: "POST",
    context: "Regenerate recovery codes failed",
  });
}

export async function logoutAllSessions(): Promise<LogoutAllResponse> {
  return apiFetch<LogoutAllResponse>("/auth/logout-all", {
    method: "POST",
    context: "Logout all sessions failed",
  });
}
