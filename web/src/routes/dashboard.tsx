import { useSession } from "@/hooks/useSession";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { PostureChart } from "@/components/dashboard/PostureChart";
import { DevicesBySiteChart } from "@/components/dashboard/DevicesBySiteChart";
import { RecentActivityTable } from "@/components/dashboard/RecentActivityTable";
import { Skeleton } from "@/components/ui/skeleton";
import { useComplianceSummary } from "@/api/hooks/useComplianceSummary";
import { useReadinessSummary } from "@/api/hooks/useReadinessSummary";
import { useNetboxSummary } from "@/api/hooks/useNetboxSummary";
import { useRecentAudit } from "@/api/hooks/useRecentAudit";
import { useComplianceDevices } from "@/api/hooks/useComplianceDevices";
import { useDevices } from "@/api/hooks/useDevices";
import type { ComplianceDeviceRow, DeviceWithEnvelope } from "@/api/types";

function inventoryToChartRows(items: DeviceWithEnvelope[]): ComplianceDeviceRow[] {
  return items.map((item) => ({
    device_id: item.facts.id,
    hostname: item.facts.hostname,
    site: item.facts.site,
    platform_family: item.facts.platform_family,
    envelope: {
      state: "unknown",
      summary: "",
      observed_version: null,
      reasons: [],
      evaluated_at: item.facts.updated_at,
    },
  }));
}

function WidgetError({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
      {message}
    </div>
  );
}

export function DashboardPage() {
  const session = useSession();
  const compliance = useComplianceSummary(session);
  const readiness = useReadinessSummary(session);
  const netbox = useNetboxSummary(session);
  const audit = useRecentAudit(session);
  const devicesSample = useComplianceDevices(session, { limit: 200 });
  const useInventoryForCharts =
    !devicesSample.isLoading &&
    !devicesSample.isError &&
    (devicesSample.data?.items.length ?? 0) === 0;
  const inventorySample = useDevices(session, { limit: 200 }, { enabled: useInventoryForCharts });

  const chartDevices =
    (devicesSample.data?.items.length ?? 0) > 0
      ? devicesSample.data!.items
      : inventoryToChartRows(inventorySample.data?.items ?? []);

  const drifted =
    compliance.data != null
      ? Math.max(
          0,
          compliance.data.total_evaluated -
            compliance.data.compliant_count -
            compliance.data.unknown_count,
        )
      : 0;

  const emptyEstate =
    compliance.data?.total_evaluated === 0 &&
    !compliance.isLoading &&
    !compliance.isError &&
    (inventorySample.data?.total_returned ?? 0) === 0;

  const pendingEvaluation =
    compliance.data?.total_evaluated === 0 &&
    !compliance.isLoading &&
    (inventorySample.data?.total_returned ?? 0) > 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-sm text-muted-foreground">Lifecycle posture at a glance</p>
      </div>

      {emptyEstate ? (
        <WidgetError message="No devices in the estate yet. Import devices from the Devices page to get started." />
      ) : null}
      {pendingEvaluation ? (
        <WidgetError message="Devices are imported but compliance has not been evaluated yet. Open Compliance and run evaluation, or re-import to trigger automatic evaluation." />
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {compliance.isLoading ? (
          <Skeleton className="h-28" />
        ) : compliance.isError ? (
          <WidgetError message="Compliance summary unavailable" />
        ) : (
          <>
            <KpiCard title="Evaluated devices" value={compliance.data?.total_evaluated ?? 0} href="/devices" />
            <KpiCard
              title="Compliant"
              value={compliance.data?.compliant_count ?? 0}
              href="/devices?compliance=compliant"
            />
            <KpiCard
              title="Drifted"
              value={drifted}
              href="/devices?compliance=outside_target"
            />
            <KpiCard
              title="Not evaluated"
              value={compliance.data?.unknown_count ?? 0}
              href="/devices?compliance=unknown"
            />
          </>
        )}
        {readiness.isLoading ? (
          <Skeleton className="h-28" />
        ) : readiness.isError ? (
          <WidgetError message="Readiness summary unavailable" />
        ) : (
          <>
            <KpiCard title="Ready for uplift" value={readiness.data?.ready_for_uplift_count ?? 0} href="/readiness" />
            <KpiCard title="Blocked" value={readiness.data?.blocked_count ?? 0} href="/readiness" />
          </>
        )}
        {netbox.isLoading ? (
          <Skeleton className="h-28" />
        ) : netbox.isError ? (
          <WidgetError message="NetBox summary unavailable" />
        ) : (
          <KpiCard title="NetBox linked" value={netbox.data?.data.netbox_linked ?? 0} href="/netbox" />
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {compliance.data ? (
          <PostureChart
            compliant={compliance.data.compliant_count}
            drifted={drifted}
            unknown={compliance.data.unknown_count}
          />
        ) : null}
        <DevicesBySiteChart devices={chartDevices} />
      </div>

      {audit.isLoading ? <Skeleton className="h-48" /> : audit.isError ? null : <RecentActivityTable items={audit.data?.items ?? []} />}
    </div>
  );
}
