import { Link } from "react-router-dom";
import { useSession } from "@/hooks/useSession";
import { useUpliftWaves } from "@/api/hooks/useUpliftWaves";
import { Table, TBody, TD, THead, TH, TR } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";

export function UpliftListPage() {
  const session = useSession();
  const waves = useUpliftWaves(session);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Uplift waves</h1>
          <p className="text-sm text-muted-foreground">Planning workspace (read-only execution)</p>
        </div>
        <Link to="/uplift/exceptions">
          <Button variant="outline">Exceptions</Button>
        </Link>
      </div>

      {waves.isLoading ? <Skeleton className="h-48" /> : (
        <Table>
          <THead>
            <TR>
              <TH>Name</TH>
              <TH>State</TH>
              <TH>Target</TH>
              <TH>Devices</TH>
              <TH>Drafted</TH>
            </TR>
          </THead>
          <TBody>
            {(waves.data?.items ?? []).map((w) => (
              <TR key={w.id}>
                <TD>
                  <Link className="font-medium hover:underline" to={`/uplift/waves/${w.id}`}>
                    {w.name}
                  </Link>
                </TD>
                <TD>
                  <Badge variant="secondary">{w.state}</Badge>
                </TD>
                <TD>{w.target_version}</TD>
                <TD>{w.device_count}</TD>
                <TD>{new Date(w.drafted_at).toLocaleString()}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}
