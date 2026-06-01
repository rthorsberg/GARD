import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/api/client";
import type { GardSession } from "@/auth/session";
import type { FirmwareTargetList } from "@/api/types";

export function useFirmwareTargets(session: GardSession) {
  return useQuery({
    queryKey: ["firmware", "targets"],
    queryFn: () =>
      apiRequest<FirmwareTargetList>(session, "/api/v1/firmware/targets", {
        searchParams: { limit: 100 },
      }),
  });
}
