import { useState } from "react";
import { useSession } from "@/hooks/useSession";
import { useAuditLog } from "@/api/hooks/useRecentAudit";
import { Table, TBody, TD, THead, TH, TR } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EvidenceDrawer } from "@/components/audit/EvidenceDrawer";

export function AuditPage() {
  const session = useSession();
  const [objectType, setObjectType] = useState("");
  const audit = useAuditLog(session, { object_type: objectType || undefined, limit: 100 });
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Audit log</h1>
        <p className="text-sm text-muted-foreground">Traceability for lifecycle operations</p>
      </div>

      <div className="flex flex-wrap gap-3">
        <input
          className="rounded-lg border border-border px-3 py-2 text-sm"
          placeholder="Filter by object type"
          value={objectType}
          onChange={(e) => setObjectType(e.target.value)}
        />
        <button type="button" className="text-sm font-medium text-muted-foreground hover:underline" onClick={() => setDrawerOpen(true)}>
          View evidence
        </button>
      </div>

      {audit.isLoading ? <Skeleton className="h-64" /> : (
        <Table>
          <THead>
            <TR>
              <TH>Timestamp</TH>
              <TH>Actor</TH>
              <TH>Action</TH>
              <TH>Object</TH>
              <TH>Result</TH>
            </TR>
          </THead>
          <TBody>
            {(audit.data?.items ?? []).map((e) => (
              <TR key={e.id}>
                <TD>{new Date(e.timestamp).toLocaleString()}</TD>
                <TD>{e.actor}</TD>
                <TD>{e.action}</TD>
                <TD>
                  {e.object_type}/{e.object_id}
                </TD>
                <TD>
                  <Badge variant={e.result === "success" ? "success" : "secondary"}>{e.result}</Badge>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}

      <EvidenceDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </div>
  );
}
