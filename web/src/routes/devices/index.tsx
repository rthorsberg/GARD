import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useSession } from "@/hooks/useSession";
import { useComplianceDevices } from "@/api/hooks/useComplianceDevices";
import { useDevices } from "@/api/hooks/useDevices";
import { useDeviceFactsIndex } from "@/api/hooks/useDeviceFactsIndex";
import { enrichComplianceRow } from "@/lib/device-display";
import { PostureBadge } from "@/components/ui/posture-badge";
import { Table, TBody, TD, THead, TH, TR } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { DeviceEmptyState } from "@/components/actions/ActionResultPanel";
import { CanAccess } from "@/auth/CanAccess";
import { Permission } from "@/auth/permissions";
import { ImportCsvDialog } from "@/components/devices/ImportCsvDialog";
import { Skeleton } from "@/components/ui/skeleton";
import type { ComplianceDeviceRow, DeviceWithEnvelope } from "@/api/types";

function inventoryToRows(items: DeviceWithEnvelope[]): ComplianceDeviceRow[] {
  return items.map((item) => ({
    device_id: item.facts.id,
    hostname: item.facts.hostname,
    region: item.facts.region,
    site: item.facts.site,
    platform_family: item.facts.platform_family,
    envelope: {
      state: "unknown",
      summary: "Imported; compliance evaluation pending",
      observed_version: null,
      reasons: [],
      evaluated_at: item.facts.updated_at,
    },
  }));
}

export function DevicesListPage() {
  const session = useSession();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [importOpen, setImportOpen] = useState(false);
  const [hostnameQ, setHostnameQ] = useState("");
  const factsIndex = useDeviceFactsIndex(session);

  const filters = useMemo(
    () => ({
      state: params.get("compliance") ?? undefined,
      site: params.get("site") ?? undefined,
      limit: Number(params.get("limit") ?? 50),
      page_token: params.get("page_token") ?? undefined,
    }),
    [params],
  );

  const compliance = useComplianceDevices(session, filters);
  const useInventoryFallback =
    !compliance.isLoading &&
    !compliance.isError &&
    (compliance.data?.items.length ?? 0) === 0 &&
    !filters.state;
  const inventory = useDevices(
    session,
    { site: filters.site, limit: filters.limit },
    { enabled: useInventoryFallback },
  );

  const isLoading =
    compliance.isLoading ||
    factsIndex.isLoading ||
    (useInventoryFallback && inventory.isLoading);
  const isError = compliance.isError || (useInventoryFallback && inventory.isError);
  const error = compliance.error ?? inventory.error;

  const sourceRows = useMemo(() => {
    if ((compliance.data?.items.length ?? 0) > 0) {
      return compliance.data!.items;
    }
    if (useInventoryFallback && inventory.data?.items.length) {
      return inventoryToRows(inventory.data.items);
    }
    return [];
  }, [compliance.data, inventory.data, useInventoryFallback]);

  const rows = useMemo(() => {
    const index = factsIndex.data;
    return sourceRows
      .map((row) => enrichComplianceRow(row, index?.get(row.device_id)))
      .filter((r) =>
        hostnameQ ? r.hostname.toLowerCase().includes(hostnameQ.toLowerCase()) : true,
      );
  }, [sourceRows, factsIndex.data, hostnameQ]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Devices</h1>
          <p className="text-sm text-muted-foreground">Estate inventory with compliance posture</p>
        </div>
        <CanAccess roles={session.roles} permission={Permission.IMPORT_DEVICES}>
          <Button onClick={() => setImportOpen(true)}>Import CSV</Button>
        </CanAccess>
      </div>

      {useInventoryFallback && (inventory.data?.items.length ?? 0) > 0 ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          Devices imported but not yet evaluated for compliance. Run evaluation on the Compliance page, or
          re-import to trigger automatic evaluation.
        </div>
      ) : null}

      <div className="flex flex-wrap gap-3">
        <input
          className="rounded-lg border border-border px-3 py-2 text-sm"
          placeholder="Search hostname"
          value={hostnameQ}
          onChange={(e) => setHostnameQ(e.target.value)}
        />
        <select
          className="rounded-lg border border-border px-3 py-2 text-sm"
          value={filters.state ?? ""}
          onChange={(e) => {
            const next = new URLSearchParams(params);
            if (e.target.value) next.set("compliance", e.target.value);
            else next.delete("compliance");
            setParams(next);
          }}
        >
          <option value="">All compliance states</option>
          <option value="compliant">Compliant</option>
          <option value="outside_target">Drifted</option>
          <option value="classified">Classified (no target)</option>
          <option value="unknown">Not evaluated</option>
        </select>
      </div>

      {isLoading ? <Skeleton className="h-64" /> : null}
      {isError ? (
        <DeviceEmptyState title="Could not load devices">{(error as Error).message}</DeviceEmptyState>
      ) : null}
      {!isLoading && !isError && rows.length === 0 ? (
        <DeviceEmptyState title="No devices match filters">Adjust filters or import devices.</DeviceEmptyState>
      ) : null}

      {rows.length > 0 ? (
        <Table>
          <THead>
            <TR>
              <TH>Hostname</TH>
              <TH>Site</TH>
              <TH>Vendor</TH>
              <TH>Model</TH>
              <TH>Platform</TH>
              <TH>Firmware</TH>
              <TH>Compliance</TH>
            </TR>
          </THead>
          <TBody>
            {rows.map((row) => (
              <TR key={row.device_id} onClick={() => navigate(`/devices/${row.device_id}`)}>
                <TD className="font-medium">{row.hostname}</TD>
                <TD>{row.site ?? "—"}</TD>
                <TD>{row.vendor}</TD>
                <TD>{row.model}</TD>
                <TD>{row.platform}</TD>
                <TD>{row.envelope.observed_version ?? "—"}</TD>
                <TD>
                  <PostureBadge state={row.envelope.state} />
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : null}

      <ImportCsvDialog open={importOpen} onClose={() => setImportOpen(false)} />
    </div>
  );
}
