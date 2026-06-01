import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/api/client";
import type { GardSession } from "@/auth/session";
import type { CatalogReloadResponse, NormalizationRuleList } from "@/api/types";
import { useFirmwareTargets } from "@/api/hooks/useFirmwareTargets";

export function useCatalogTargets(session: GardSession) {
  return useFirmwareTargets(session);
}

export function useCatalogUpgradePaths(session: GardSession) {
  return useQuery({
    queryKey: ["firmware", "upgrade-paths"],
    queryFn: () =>
      apiRequest<{ items: UpgradePathEdge[]; total_returned: number }>(
        session,
        "/api/v1/firmware/upgrade-paths/edges",
        { searchParams: { limit: 200 } },
      ),
  });
}

export interface UpgradePathEdge {
  id: string;
  platform_family: string;
  from_version: string;
  to_version: string;
  weight: number;
  notes?: string | null;
}

export function useDbNormalizationRules(session: GardSession) {
  return useQuery({
    queryKey: ["catalog", "normalization-rules"],
    queryFn: () =>
      apiRequest<NormalizationRuleList>(session, "/api/v1/admin/catalog/normalization/rules"),
    retry: false,
  });
}

export function useCatalogReload(session: GardSession) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiRequest<CatalogReloadResponse>(session, "/api/v1/admin/catalog/reload", { method: "POST" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["firmware"] });
      void qc.invalidateQueries({ queryKey: ["compliance"] });
      void qc.invalidateQueries({ queryKey: ["readiness"] });
      void qc.invalidateQueries({ queryKey: ["catalog"] });
    },
  });
}

export function useUpsertTarget(session: GardSession) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: UpsertTargetBody) =>
      apiRequest<CatalogReloadResponse>(session, "/api/v1/admin/catalog/firmware/targets", {
        method: "PUT",
        body,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["firmware"] });
      void qc.invalidateQueries({ queryKey: ["compliance"] });
    },
  });
}

export interface UpsertTargetBody {
  name: string;
  platform_family: string;
  target_version: string;
  scope_selector: Record<string, string>;
  notes?: string;
}

export function useAddUpgradeEdge(session: GardSession) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AddEdgeBody) =>
      apiRequest<CatalogReloadResponse>(session, "/api/v1/admin/catalog/firmware/upgrade-paths/edges", {
        method: "POST",
        body,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["firmware"] });
    },
  });
}

export interface AddEdgeBody {
  platform_family: string;
  from_version: string;
  to_version: string;
  weight?: number;
  notes?: string;
}

export function useCreateNormRule(session: GardSession) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateNormRuleBody) =>
      apiRequest(session, "/api/v1/admin/catalog/normalization/rules", {
        method: "POST",
        body: { ...body, renormalize: true },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["catalog"] });
      void qc.invalidateQueries({ queryKey: ["devices"] });
      void qc.invalidateQueries({ queryKey: ["compliance"] });
    },
  });
}

export interface CreateNormRuleBody {
  model_pattern: string;
  vendor_normalized: string;
  platform_family: string;
  model_normalized?: string;
  priority?: number;
  notes?: string;
}

export function useRenormalizeEstate(session: GardSession) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiRequest<{ devices_updated: number }>(session, "/api/v1/admin/catalog/devices/renormalize", {
        method: "POST",
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["devices"] });
      void qc.invalidateQueries({ queryKey: ["compliance"] });
    },
  });
}
