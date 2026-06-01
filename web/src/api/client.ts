import type { GardSession } from "../auth/session";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export interface ApiRequestInit extends Omit<RequestInit, "body"> {
  body?: unknown;
  searchParams?: Record<string, string | number | boolean | undefined | null>;
}

function buildUrl(session: GardSession, path: string, searchParams?: ApiRequestInit["searchParams"]): string {
  const base = session.apiBaseUrl || "";
  const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;
  if (!searchParams) return url;
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(searchParams)) {
    if (v !== undefined && v !== null && v !== "") {
      sp.set(k, String(v));
    }
  }
  const qs = sp.toString();
  return qs ? `${url}?${qs}` : url;
}

function friendlyMessage(status: number, detail: unknown): string {
  if (status === 401) return "Session expired or invalid token. Please sign in again.";
  if (status === 403) return "You do not have permission for this action.";
  if (status === 404) return "Resource not found.";
  if (status >= 502) return "GARD service is temporarily unavailable.";
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "error" in detail) {
    const err = (detail as { error?: { message?: string } }).error;
    if (err?.message) return err.message;
  }
  if (detail && typeof detail === "object" && "detail" in detail) {
    const d = (detail as { detail?: unknown }).detail;
    if (typeof d === "string") return d;
  }
  return `Request failed (${status})`;
}

export async function apiRequest<T>(
  session: GardSession,
  path: string,
  init: ApiRequestInit = {},
): Promise<T> {
  const { searchParams, body, headers, ...rest } = init;
  const url = buildUrl(session, path, searchParams);

  const res = await fetch(url, {
    ...rest,
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${session.token}`,
      "X-Correlation-ID": crypto.randomUUID(),
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 204) {
    return undefined as T;
  }

  let payload: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!res.ok) {
    throw new ApiError(friendlyMessage(res.status, payload), res.status);
  }

  return payload as T;
}

export async function apiUpload<T>(
  session: GardSession,
  path: string,
  formData: FormData,
  searchParams?: ApiRequestInit["searchParams"],
): Promise<T> {
  const url = buildUrl(session, path, searchParams);
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${session.token}`,
      "X-Correlation-ID": crypto.randomUUID(),
    },
    body: formData,
  });
  const payload = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ApiError(friendlyMessage(res.status, payload), res.status);
  }
  return payload as T;
}

export async function healthCheck(session: GardSession): Promise<boolean> {
  const url = buildUrl(session, "/healthz");
  try {
    const res = await fetch(url);
    return res.ok;
  } catch {
    return false;
  }
}
