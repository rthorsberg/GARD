import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/api/client";
import type { GardSession } from "@/auth/session";
import type { WaveList, WaveEnvelope, ExceptionList } from "@/api/types";

export function useUpliftWaves(session: GardSession) {
  return useQuery({
    queryKey: ["uplift", "waves"],
    queryFn: () => apiRequest<WaveList>(session, "/api/v1/uplift/waves"),
  });
}

export function useUpliftWaveDetail(session: GardSession, waveId: string) {
  return useQuery({
    queryKey: ["uplift", "wave", waveId],
    queryFn: () => apiRequest<WaveEnvelope>(session, `/api/v1/uplift/waves/${waveId}`),
    enabled: Boolean(waveId),
  });
}

export function useUpliftExceptions(session: GardSession) {
  return useQuery({
    queryKey: ["uplift", "exceptions"],
    queryFn: () => apiRequest<ExceptionList>(session, "/api/v1/uplift/exceptions"),
  });
}
