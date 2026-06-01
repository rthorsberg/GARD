import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/api/client";
import type { GardSession } from "@/auth/session";
import type { EvidencePage } from "@/api/types";

export function useEvidenceList(session: GardSession, limit = 20) {
  return useQuery({
    queryKey: ["evidence", limit],
    queryFn: () => apiRequest<EvidencePage>(session, "/api/v1/evidence", { searchParams: { limit } }),
  });
}
