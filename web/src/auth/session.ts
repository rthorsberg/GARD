export interface GardSession {
  apiBaseUrl: string;
  token: string;
  subject: string;
  roles: string[];
  expiresAt: string;
  environment?: string;
}

const STORAGE_KEY = "gard.session";

export function loadSession(): GardSession | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as GardSession;
    if (!parsed.token || !parsed.expiresAt) return null;
    if (new Date(parsed.expiresAt).getTime() <= Date.now()) {
      clearSession();
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function saveSession(session: GardSession): void {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  sessionStorage.removeItem(STORAGE_KEY);
}

export function parseJwtPayload(token: string): {
  sub?: string;
  roles?: string[];
  exp?: number;
} {
  const parts = token.split(".");
  if (parts.length < 2) return {};
  try {
    const json = atob(parts[1].replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(json) as { sub?: string; roles?: string[]; exp?: number };
  } catch {
    return {};
  }
}

export function sessionFromToken(
  token: string,
  apiBaseUrl: string,
  environment?: string,
): GardSession {
  const payload = parseJwtPayload(token.trim());
  const exp = payload.exp ? new Date(payload.exp * 1000).toISOString() : new Date(Date.now() + 86400000).toISOString();
  return {
    apiBaseUrl: apiBaseUrl.replace(/\/$/, ""),
    token: token.trim(),
    subject: payload.sub ?? "unknown",
    roles: Array.isArray(payload.roles) ? payload.roles : [],
    expiresAt: exp,
    environment,
  };
}

export function apiRoot(session: GardSession): string {
  return session.apiBaseUrl || "";
}
