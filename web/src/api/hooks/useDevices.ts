import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/api/client";
import type { GardSession } from "@/auth/session";
import type { DeviceList } from "@/api/types";

export interface InventoryListFilters {
  site?: string;
  vendor_normalized?: string;
  limit?: number;
}

export function useDevices(
  session: GardSession,
  filters: InventoryListFilters,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: ["devices", "list", filters],
    queryFn: () =>
      apiRequest<DeviceList>(session, "/api/v1/devices", {
        searchParams: {
          site: filters.site,
          vendor_normalized: filters.vendor_normalized,
          limit: filters.limit ?? 50,
        },
      }),
    enabled: options?.enabled ?? true,
  });
}
