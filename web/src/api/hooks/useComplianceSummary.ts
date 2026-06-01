import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/api/client";
import type { GardSession } from "@/auth/session";
import type { ComplianceSummary } from "@/api/types";

export function useComplianceSummary(session: GardSession) {
  return useQuery({
    queryKey: ["compliance", "summary"],
    queryFn: () => apiRequest<ComplianceSummary>(session, "/api/v1/compliance/summary"),
    retry: (count, err) => (err as { status?: number }).status !== 403 && count < 2,
  });
}
