import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSession } from "@/hooks/useSession";
import { useNetboxSummary } from "@/api/hooks/useNetboxSummary";
import { useNetboxSync } from "@/api/hooks/useNetboxSync";
import { apiRequest } from "@/api/client";
import type { NetboxSyncRunList } from "@/api/types";
import { CanAccess } from "@/auth/CanAccess";
import { Permission } from "@/auth/permissions";
import { Button } from "@/components/ui/button";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { ActionResultPanel, type ActionResult } from "@/components/actions/ActionResultPanel";
import { Table, TBody, TD, THead, TH, TR } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/useToast";

export function NetboxPage() {
  const session = useSession();
  const summary = useNetboxSummary(session);
  const sync = useNetboxSync(session);
  const runs = useQuery({
    queryKey: ["netbox", "runs"],
    queryFn: () => apiRequest<NetboxSyncRunList>(session, "/api/v1/integrations/netbox/sync-runs", { searchParams: { limit: 20 } }),
  });
  const { toast } = useToast();
  const [result, setResult] = useState<ActionResult | null>(null);
  const [confirmWriteback, setConfirmWriteback] = useState(false);

  async function runSync() {
    try {
      const res = await sync.mutateAsync(confirmWriteback);
      const report = res.data.report;
      const wb = report?.writeback?.summary;
      setResult({
        action: "netbox_sync",
        status: wb && wb.failed > 0 ? "partial" : "success",
        summary: "NetBox sync completed",
        counts: {
          matched: report?.matched_count ?? 0,
          created: report?.created_count ?? 0,
          updated: report?.updated_count ?? 0,
          orphaned: report?.orphaned_count ?? 0,
          writeback_updated: wb?.updated ?? 0,
          writeback_failed: wb?.failed ?? 0,
        },
      });
      toast("NetBox sync completed");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">NetBox integration</h1>
          <p className="text-sm text-muted-foreground">Sync pull and lifecycle write-back visibility</p>
        </div>
        <CanAccess roles={session.roles} permission={Permission.SYNC_NETBOX}>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={confirmWriteback} onChange={(e) => setConfirmWriteback(e.target.checked)} />
              Confirm write-back
            </label>
            <Button onClick={() => void runSync()} disabled={sync.isPending}>
              {sync.isPending ? "Syncing…" : "Run sync"}
            </Button>
          </div>
        </CanAccess>
      </div>

      {summary.isLoading ? <Skeleton className="h-28" /> : summary.data ? (
        <div className="grid gap-4 md:grid-cols-3">
          <KpiCard title="NetBox linked" value={summary.data.data.netbox_linked} />
          <KpiCard title="CSV only" value={summary.data.data.csv_only} />
          <KpiCard
            title="Last sync"
            value={summary.data.data.last_sync_at ? new Date(summary.data.data.last_sync_at).toLocaleString() : "Never"}
          />
        </div>
      ) : null}

      <ActionResultPanel result={result} />

      {runs.isLoading ? <Skeleton className="h-48" /> : (
        <Table>
          <THead>
            <TR>
              <TH>Started</TH>
              <TH>Status</TH>
              <TH>Matched</TH>
              <TH>Created</TH>
              <TH>Updated</TH>
            </TR>
          </THead>
          <TBody>
            {(runs.data?.data ?? []).map((r) => (
              <TR key={r.id}>
                <TD>{new Date(r.started_at).toLocaleString()}</TD>
                <TD>{r.status}</TD>
                <TD>{r.matched_count}</TD>
                <TD>{r.created_count}</TD>
                <TD>{r.updated_count}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}
