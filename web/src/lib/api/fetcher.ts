import { clearAuthSession, ensureFreshAuthSession } from "@/lib/auth";

export const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:7700";

export interface ProblemDetail {
  type?: string;
  title?: string;
  status: number;
  detail: string;
  error_code?: string;
}

export class ApiHttpError extends Error {
  status: number;
  body: string;
  problem: ProblemDetail | null;

  constructor(context: string, status: number, body: string) {
    super(`${context} ${status}: ${body}`);
    this.name = "ApiHttpError";
    this.status = status;
    this.body = body;
    this.problem = ApiHttpError._parse(body);
  }

  get errorCode(): string | undefined {
    return this.problem?.error_code;
  }

  private static _parse(body: string): ProblemDetail | null {
    try {
      const parsed = JSON.parse(body);
      if (parsed && typeof parsed.detail === "string") return parsed as ProblemDetail;
    } catch {
      /* not JSON */
    }
    return null;
  }
}

export async function authHeaders(): Promise<Record<string, string>> {
  const session = await ensureFreshAuthSession();
  if (!session?.token) {
    return {};
  }
  return { Authorization: `Bearer ${session.token}` };
}

export type ApiQueryValue = string | number | boolean | null | undefined;
type ApiRequestInit = Omit<RequestInit, "body"> & {
  body?: BodyInit | null;
  json?: unknown;
  context?: string;
  includeAuth?: boolean;
  clearOn401?: boolean;
};

export function buildApiUrl(
  path: string,
  params?: Record<string, ApiQueryValue>
): string {
  if (!params) {
    return path;
  }
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") {
      continue;
    }
    search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

async function _executeRequest(path: string, init: ApiRequestInit): Promise<Response> {
  const {
    context = "API",
    json,
    headers: rawHeaders,
    body: rawBody,
    includeAuth = true,
    clearOn401 = true,
    ...rest
  } = init;
  const headers = new Headers(rawHeaders);
  if (includeAuth) {
    const auth = await authHeaders();
    for (const [key, value] of Object.entries(auth)) {
      if (value !== undefined) {
        headers.set(key, value);
      }
    }
  }
  let body: BodyInit | null | undefined = rawBody;
  if (json !== undefined) {
    if (!headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    body = JSON.stringify(json);
  }
  const res = await fetch(`${BASE_URL}${path}`, {
    ...rest,
    headers,
    body,
  });
  if (clearOn401 && res.status === 401) {
    clearAuthSession();
  }
  if (!res.ok) {
    const text = await res.text();
    throw new ApiHttpError(context, res.status, text);
  }
  return res;
}

export async function apiFetch<T>(
  path: string,
  init: ApiRequestInit = {}
): Promise<T> {
  const res = await _executeRequest(path, init);
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export async function apiFetchBlob(
  path: string,
  init: ApiRequestInit = {}
): Promise<Blob> {
  const res = await _executeRequest(path, init);
  return res.blob();
}

export async function fetcher<T>(path: string): Promise<T> {
  return apiFetch<T>(path);
}
