import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/api/client";
import type { GardSession } from "@/auth/session";
import type { NetboxSyncEnvelope } from "@/api/types";

export function useNetboxSync(session: GardSession) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (confirmWriteback: boolean) =>
      apiRequest<NetboxSyncEnvelope>(session, "/api/v1/integrations/netbox/sync", {
        method: "POST",
        searchParams: { confirm_writeback: confirmWriteback },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["netbox"] });
    },
  });
}
