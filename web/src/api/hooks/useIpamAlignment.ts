import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/api/client";
import type { IpamAlignmentFindingList } from "@/api/types";
import type { SessionContext } from "@/hooks/useSession";

export function useIpamAlignmentFindings(
  session: SessionContext,
  params?: { run_id?: string; device_id?: string; severity?: string },
) {
  return useQuery({
    queryKey: ["netbox", "alignment", "findings", params],
    queryFn: () =>
      apiRequest<IpamAlignmentFindingList>(
        session,
        "/api/v1/integrations/netbox/alignment/findings",
        { searchParams: params as Record<string, string> },
      ),
    enabled: Boolean(params?.run_id || params?.device_id),
  });
}
