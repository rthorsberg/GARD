import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/api/client";
import type { GardSession } from "@/auth/session";
import type { ComplianceDeviceList } from "@/api/types";

export interface DeviceListFilters {
  state?: string;
  site?: string;
  vendor_normalized?: string;
  limit?: number;
  page_token?: string;
}

export function useComplianceDevices(session: GardSession, filters: DeviceListFilters) {
  return useQuery({
    queryKey: ["compliance", "devices", filters],
    queryFn: () =>
      apiRequest<ComplianceDeviceList>(session, "/api/v1/compliance/devices", {
        searchParams: {
          state: filters.state,
          site: filters.site,
          vendor_normalized: filters.vendor_normalized,
          limit: filters.limit ?? 50,
          page_token: filters.page_token,
        },
      }),
  });
}
