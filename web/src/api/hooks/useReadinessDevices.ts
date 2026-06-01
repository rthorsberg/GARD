import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/api/client";
import type { GardSession } from "@/auth/session";
import type { ReadinessDeviceList } from "@/api/types";

export interface ReadinessListFilters {
  state?: string;
  site?: string;
  limit?: number;
  page_token?: string;
}

export function useReadinessDevices(session: GardSession, filters: ReadinessListFilters) {
  return useQuery({
    queryKey: ["readiness", "devices", filters],
    queryFn: () =>
      apiRequest<ReadinessDeviceList>(session, "/api/v1/readiness/devices", {
        searchParams: {
          state: filters.state,
          site: filters.site,
          limit: filters.limit ?? 50,
          page_token: filters.page_token,
        },
      }),
  });
}
