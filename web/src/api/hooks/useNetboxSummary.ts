import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/api/client";
import type { GardSession } from "@/auth/session";
import type { NetboxSummaryEnvelope } from "@/api/types";

export function useNetboxSummary(session: GardSession) {
  return useQuery({
    queryKey: ["netbox", "summary"],
    queryFn: () => apiRequest<NetboxSummaryEnvelope>(session, "/api/v1/integrations/netbox/summary"),
  });
}
