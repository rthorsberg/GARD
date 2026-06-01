import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/api/client";
import type { GardSession } from "@/auth/session";
import type { ReadinessSummary } from "@/api/types";

export function useReadinessSummary(session: GardSession) {
  return useQuery({
    queryKey: ["readiness", "summary"],
    queryFn: () => apiRequest<ReadinessSummary>(session, "/api/v1/readiness/summary"),
  });
}
