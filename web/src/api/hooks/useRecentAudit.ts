import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/api/client";
import type { GardSession } from "@/auth/session";
import type { AuditPage } from "@/api/types";

export function useRecentAudit(session: GardSession, limit = 10) {
  return useQuery({
    queryKey: ["audit", "recent", limit],
    queryFn: () => apiRequest<AuditPage>(session, "/api/v1/audit", { searchParams: { limit } }),
  });
}

export function useAuditLog(
  session: GardSession,
  filters: { object_type?: string; actor?: string; limit?: number },
) {
  return useQuery({
    queryKey: ["audit", filters],
    queryFn: () =>
      apiRequest<AuditPage>(session, "/api/v1/audit", {
        searchParams: {
          object_type: filters.object_type,
          actor: filters.actor,
          limit: filters.limit ?? 50,
        },
      }),
  });
}
