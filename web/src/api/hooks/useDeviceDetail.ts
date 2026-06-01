import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/api/client";
import type { GardSession } from "@/auth/session";
import type { DeviceWithEnvelope, ReadinessEnvelope, ComplianceEnvelope } from "@/api/types";

export function useDeviceDetail(session: GardSession, deviceId: string) {
  return useQuery({
    queryKey: ["device", deviceId],
    queryFn: () => apiRequest<DeviceWithEnvelope>(session, `/api/v1/devices/${deviceId}`),
    enabled: Boolean(deviceId),
  });
}

export function useDeviceCompliance(session: GardSession, deviceId: string) {
  return useQuery({
    queryKey: ["device", deviceId, "compliance"],
    queryFn: () => apiRequest<ComplianceEnvelope>(session, `/api/v1/devices/${deviceId}/compliance`),
    enabled: Boolean(deviceId),
  });
}

export function useDeviceReadiness(session: GardSession, deviceId: string) {
  return useQuery({
    queryKey: ["device", deviceId, "readiness"],
    queryFn: () => apiRequest<ReadinessEnvelope>(session, `/api/v1/devices/${deviceId}/readiness`),
    enabled: Boolean(deviceId),
  });
}
