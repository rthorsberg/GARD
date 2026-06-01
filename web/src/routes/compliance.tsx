import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "@/hooks/useSession";
import { useComplianceSummary } from "@/api/hooks/useComplianceSummary";
import { useComplianceDevices } from "@/api/hooks/useComplianceDevices";
import { useComplianceEvaluate } from "@/api/hooks/useComplianceEvaluate";
import { useFirmwareTargets } from "@/api/hooks/useFirmwareTargets";
import { useDeviceFactsIndex } from "@/api/hooks/useDeviceFactsIndex";
import { enrichComplianceRow } from "@/lib/device-display";
import { CanAccess } from "@/auth/CanAccess";
import { Permission } from "@/auth/permissions";
import { Button } from "@/components/ui/button";
import { PostureChart } from "@/components/dashboard/PostureChart";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { ActionResultPanel, type ActionResult } from "@/components/actions/ActionResultPanel";
import { Table, TBody, TD, THead, TH, TR } from "@/components/ui/table";
import { PostureBadge } from "@/components/ui/posture-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/useToast";

export function CompliancePage() {
  const session = useSession();
  const summary = useComplianceSummary(session);
  const devices = useComplianceDevices(session, { limit: 100 });
  const targets = useFirmwareTargets(session);
  const factsIndex = useDeviceFactsIndex(session);
  const evaluate = useComplianceEvaluate(session);
  const { toast } = useToast();
  const [result, setResult] = useState<ActionResult | null>(null);

  const drifted =
    summary.data != null
      ? Math.max(0, summary.data.total_evaluated - summary.data.compliant_count - summary.data.unknown_count)
      : 0;

  const catalogEmpty = !targets.isLoading && (targets.data?.total_returned ?? 0) === 0;
  const catalogDrift = summary.data?.counts_by_drift_type.catalog_drift ?? 0;

  const deviceRows = useMemo(() => {
    const index = factsIndex.data;
    return (devices.data?.items ?? []).map((row) => enrichComplianceRow(row, index?.get(row.device_id)));
  }, [devices.data, factsIndex.data]);

  async function runEval() {
    try {
      const res = await evaluate.mutateAsync();
      setResult({
        action: "compliance_evaluate",
        status: "success",
        summary: "Compliance evaluation completed",
        counts: {
          requested: res.requested_count,
          evaluated: res.evaluated_count,
          unchanged: res.unchanged_count,
        },
      });
      toast("Compliance evaluation completed");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Compliance</h1>
          <p className="text-sm text-muted-foreground">Fleet drift, firmware targets, and evaluation</p>
        </div>
        <CanAccess roles={session.roles} permission={Permission.RUN_COMPLIANCE_EVAL}>
          <Button onClick={() => void runEval()} disabled={evaluate.isPending}>
            {evaluate.isPending ? "Running…" : "Run evaluation"}
          </Button>
        </CanAccess>
      </div>

      {catalogEmpty ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          <p className="font-medium">Firmware catalog is empty</p>
          <p className="mt-1">
            No live firmware targets are loaded ({catalogDrift} devices show catalog drift). Open{" "}
            <Link className="font-medium underline" to="/catalog">
              Catalog
            </Link>{" "}
            to define targets and upgrade paths, then run evaluation again.
          </p>
        </div>
      ) : null}

      {summary.isLoading ? <Skeleton className="h-64" /> : null}
      {summary.data ? (
        <>
          <div className="grid gap-4 md:grid-cols-4">
            <KpiCard title="Evaluated" value={summary.data.total_evaluated} href="/devices" />
            <KpiCard title="Compliant" value={summary.data.compliant_count} href="/devices?compliance=compliant" />
            <KpiCard title="Drifted" value={drifted} href="/devices?compliance=outside_target" />
            <KpiCard title="Catalog drift" value={summary.data.counts_by_drift_type.catalog_drift} href="/devices?compliance=classified" />
          </div>
          <PostureChart
            compliant={summary.data.compliant_count}
            drifted={drifted}
            unknown={summary.data.unknown_count}
          />
        </>
      ) : null}

      <div>
        <h2 className="mb-3 text-lg font-semibold">Firmware targets (read-only)</h2>
        {targets.isLoading ? <Skeleton className="h-32" /> : (targets.data?.items.length ?? 0) === 0 ? (
          <p className="text-sm text-muted-foreground">No targets loaded. See catalog reload instructions above.</p>
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Name</TH>
                <TH>Platform</TH>
                <TH>Target version</TH>
                <TH>Scope</TH>
              </TR>
            </THead>
            <TBody>
              {targets.data!.items.map((t) => (
                <TR key={t.id}>
                  <TD className="font-medium">{t.name}</TD>
                  <TD>{t.platform_family}</TD>
                  <TD>{t.target_version}</TD>
                  <TD className="text-xs text-muted-foreground">{JSON.stringify(t.scope_selector)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </div>

      <div>
        <h2 className="mb-3 text-lg font-semibold">Devices by compliance state</h2>
        {devices.isLoading || factsIndex.isLoading ? (
          <Skeleton className="h-48" />
        ) : deviceRows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No evaluated devices. Import inventory and run evaluation.</p>
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Hostname</TH>
                <TH>Vendor</TH>
                <TH>Model</TH>
                <TH>Firmware</TH>
                <TH>Drift</TH>
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
                  <TD>{row.envelope.observed_version ?? "—"}</TD>
                  <TD className="text-sm text-muted-foreground">{row.envelope.drift_type ?? "—"}</TD>
                  <TD>
                    <PostureBadge state={row.envelope.state} />
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
