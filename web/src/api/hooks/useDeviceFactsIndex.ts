import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/api/client";
import type { GardSession } from "@/auth/session";
import type { DeviceFacts, DeviceList } from "@/api/types";

export function useDeviceFactsIndex(session: GardSession, limit = 500) {
  return useQuery({
    queryKey: ["devices", "index", limit],
    queryFn: async () => {
      const res = await apiRequest<DeviceList>(session, "/api/v1/devices", {
        searchParams: { limit },
      });
      const map = new Map<string, DeviceFacts>();
      for (const item of res.items) {
        map.set(item.facts.id, item.facts);
      }
      return map;
    },
  });
}
