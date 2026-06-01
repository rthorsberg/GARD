import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "@/hooks/useSession";
import { useReadinessSummary } from "@/api/hooks/useReadinessSummary";
import { useReadinessDevices } from "@/api/hooks/useReadinessDevices";
import { useReadinessEvaluate } from "@/api/hooks/useComplianceEvaluate";
import { useDeviceFactsIndex } from "@/api/hooks/useDeviceFactsIndex";
import { CanAccess } from "@/auth/CanAccess";
import { Permission } from "@/auth/permissions";
import { Button } from "@/components/ui/button";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { ActionResultPanel, type ActionResult } from "@/components/actions/ActionResultPanel";
import { Table, TBody, TD, THead, TH, TR } from "@/components/ui/table";
import { PostureBadge } from "@/components/ui/posture-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/useToast";

export function ReadinessPage() {
  const session = useSession();
  const summary = useReadinessSummary(session);
  const devices = useReadinessDevices(session, { limit: 100 });
  const factsIndex = useDeviceFactsIndex(session);
  const evaluate = useReadinessEvaluate(session);
  const { toast } = useToast();
  const [result, setResult] = useState<ActionResult | null>(null);

  const deviceRows = useMemo(() => {
    const index = factsIndex.data;
    return (devices.data?.items ?? []).map((row) => {
      const facts = index?.get(row.device_id);
      return {
        ...row,
        vendor: facts?.vendor_normalized ?? facts?.vendor_raw ?? "—",
        model: facts?.model_normalized ?? facts?.model_raw ?? "—",
      };
    });
  }, [devices.data, factsIndex.data]);

  async function runEval() {
    try {
      const res = await evaluate.mutateAsync();
      setResult({
        action: "readiness_evaluate",
        status: "success",
        summary: "Readiness evaluation completed",
        counts: {
          requested: res.requested_count,
          evaluated: res.evaluated_count,
          unchanged: res.unchanged_count,
        },
      });
      toast("Readiness evaluation completed");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Readiness</h1>
          <p className="text-sm text-muted-foreground">Prerequisite posture across the estate</p>
        </div>
        <CanAccess roles={session.roles} permission={Permission.RUN_READINESS_EVAL}>
          <Button onClick={() => void runEval()} disabled={evaluate.isPending}>
            {evaluate.isPending ? "Running…" : "Run evaluation"}
          </Button>
        </CanAccess>
      </div>

      {summary.isLoading ? (
        <div className="grid gap-4 md:grid-cols-3">
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
          <Skeleton className="h-28" />
        </div>
      ) : summary.data ? (
        <div className="grid gap-4 md:grid-cols-3">
          <KpiCard title="Ready for uplift" value={summary.data.ready_for_uplift_count} />
          <KpiCard title="Blocked" value={summary.data.blocked_count} />
          <KpiCard title="Not applicable" value={summary.data.not_applicable_count} />
        </div>
      ) : null}

      <div>
        <h2 className="mb-3 text-lg font-semibold">Devices by readiness</h2>
        {devices.isLoading || factsIndex.isLoading ? (
          <Skeleton className="h-48" />
        ) : deviceRows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No readiness evaluations yet. Run evaluation after compliance.</p>
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Hostname</TH>
                <TH>Vendor</TH>
                <TH>Model</TH>
                <TH>State</TH>
              </TR>
            </THead>
            <TBody>
              {deviceRows.map((row) => (
                <TR key={row.device_id}>
                  <TD>
                    <Link className="font-medium hover:underline" to={`/devices/${row.device_id}`}>
                      {row.hostname}
                    </Link>
                  </TD>
                  <TD>{row.vendor}</TD>
                  <TD>{row.model}</TD>
                  <TD>
                    <PostureBadge state={row.envelope.state} domain="readiness" />
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </div>

      <ActionResultPanel result={result} />
    </div>
  );
}
