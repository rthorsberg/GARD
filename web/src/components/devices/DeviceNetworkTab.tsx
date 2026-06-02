import { useSession } from "@/hooks/useSession";
import { useDeviceNetworkContext } from "@/api/hooks/useDeviceNetworkContext";
import { useIpamAlignmentFindings } from "@/api/hooks/useIpamAlignment";
import { Table, TBody, TD, THead, TH, TR } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";

export function DeviceNetworkTab({ deviceId }: { deviceId: string }) {
  const session = useSession();
  const ctx = useDeviceNetworkContext(session, deviceId);
  const findings = useIpamAlignmentFindings(session, { device_id: deviceId });

  if (ctx.isLoading) return <Skeleton className="h-48" />;

  if (ctx.isError || !ctx.data) {
    return (
      <p className="text-sm text-muted-foreground">
        No network context snapshot yet. Run a NetBox sync with IPAM alignment enabled.
      </p>
    );
  }

  const data = ctx.data;

  return (
    <div className="space-y-6">
      <dl className="grid gap-3 text-sm md:grid-cols-2">
        <div>
          <dt className="text-muted-foreground">Resolved management IP</dt>
          <dd className="font-medium">{data.resolved_mgmt_ip ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Resolution method</dt>
          <dd>{data.mgmt_resolution_method ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Primary IPv4</dt>
          <dd>{data.primary_ip4 ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Captured</dt>
          <dd>{new Date(data.captured_at).toLocaleString()}</dd>
        </div>
      </dl>

      {findings.data && findings.data.items.length > 0 ? (
        <div>
          <h3 className="mb-2 text-sm font-semibold">Alignment findings</h3>
          <Table>
            <THead>
              <TR>
                <TH>Kind</TH>
                <TH>Severity</TH>
                <TH>Status</TH>
                <TH>Interface</TH>
              </TR>
            </THead>
            <TBody>
              {findings.data.items.map((f) => (
                <TR key={f.id}>
                  <TD>{f.kind}</TD>
                  <TD>
                    <Badge variant={f.severity === "error" ? "destructive" : "secondary"}>
                      {f.severity}
                    </Badge>
                  </TD>
                  <TD>{f.status}</TD>
                  <TD>{f.interface_name ?? "—"}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </div>
      ) : null}

      <div>
        <h3 className="mb-2 text-sm font-semibold">Interfaces</h3>
        <Table>
          <THead>
            <TR>
              <TH>Name</TH>
              <TH>Mode</TH>
              <TH>Addresses</TH>
            </TR>
          </THead>
          <TBody>
            {data.interfaces.map((iface, i) => (
              <TR key={i}>
                <TD>{String(iface.name ?? "—")}</TD>
                <TD>{String(iface.mode ?? "—")}</TD>
                <TD>
                  {Array.isArray(iface.addresses)
                    ? (iface.addresses as { address?: string }[])
                        .map((a) => a.address)
                        .filter(Boolean)
                        .join(", ") || "—"
                    : "—"}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </div>
    </div>
  );
}
