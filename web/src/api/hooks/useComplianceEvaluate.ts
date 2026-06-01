import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/api/client";
import type { GardSession } from "@/auth/session";
import type { EvaluateResponse } from "@/api/types";

export function useComplianceEvaluate(session: GardSession) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiRequest<EvaluateResponse>(session, "/api/v1/compliance/evaluate", {
        method: "POST",
        body: { scope_selector: {} },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["compliance"] });
    },
  });
}

export function useReadinessEvaluate(session: GardSession) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiRequest<EvaluateResponse>(session, "/api/v1/readiness/evaluate", {
        method: "POST",
        body: { scope_selector: {} },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["readiness"] });
    },
  });
}
