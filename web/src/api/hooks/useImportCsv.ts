import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest, apiUpload } from "@/api/client";
import { hasPermission, Permission } from "@/auth/permissions";
import type { GardSession } from "@/auth/session";
import type { EvaluateResponse, ImportSummary } from "@/api/types";

export interface ImportCsvResult {
  summary: ImportSummary;
  compliance?: EvaluateResponse;
  readiness?: EvaluateResponse;
  evaluationWarning?: string;
}

export function useImportCsv(session: GardSession) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File): Promise<ImportCsvResult> => {
      const fd = new FormData();
      fd.append("file", file);
      const summary = await apiUpload<ImportSummary>(session, "/api/v1/imports/devices/csv", fd);

      const imported =
        summary.totals.devices_created > 0 ||
        summary.totals.devices_updated > 0 ||
        summary.totals.rows_accepted > 0;

      if (!imported) {
        return { summary };
      }

      let compliance: EvaluateResponse | undefined;
      let readiness: EvaluateResponse | undefined;
      let evaluationWarning: string | undefined;

      try {
        if (hasPermission(session.roles, Permission.RUN_COMPLIANCE_EVAL)) {
          compliance = await apiRequest<EvaluateResponse>(session, "/api/v1/compliance/evaluate", {
            method: "POST",
            body: { scope_selector: {} },
          });
        }
        if (hasPermission(session.roles, Permission.RUN_READINESS_EVAL)) {
          readiness = await apiRequest<EvaluateResponse>(session, "/api/v1/readiness/evaluate", {
            method: "POST",
            body: { scope_selector: {} },
          });
        }
      } catch (e) {
        evaluationWarning = (e as Error).message;
      }

      return { summary, compliance, readiness, evaluationWarning };
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["compliance"] });
      void qc.invalidateQueries({ queryKey: ["readiness"] });
      void qc.invalidateQueries({ queryKey: ["devices"] });
      void qc.invalidateQueries({ queryKey: ["device"] });
      void qc.invalidateQueries({ queryKey: ["audit"] });
    },
  });
}
