import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/api/client";
import type { DeviceNetworkContextOut } from "@/api/types";
import type { SessionContext } from "@/hooks/useSession";

export function useDeviceNetworkContext(session: SessionContext, deviceId: string) {
  return useQuery({
    queryKey: ["devices", deviceId, "network-context"],
    queryFn: () =>
      apiRequest<DeviceNetworkContextOut>(
        session,
        `/api/v1/devices/${deviceId}/network-context`,
      ),
    enabled: Boolean(deviceId),
    retry: false,
  });
}
