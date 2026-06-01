import { Link } from "react-router-dom";
import { useSession } from "@/hooks/useSession";
import { useUpliftExceptions } from "@/api/hooks/useUpliftWaves";
import { Table, TBody, TD, THead, TH, TR } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

export function UpliftExceptionsPage() {
  const session = useSession();
  const exceptions = useUpliftExceptions(session);

  return (
    <div className="space-y-6">
      <div>
        <Link to="/uplift" className="text-sm text-muted-foreground hover:underline">
          ← Waves
        </Link>
        <h1 className="text-2xl font-bold">Uplift exceptions</h1>
      </div>
      {exceptions.isLoading ? <Skeleton className="h-48" /> : (
        <Table>
          <THead>
            <TR>
              <TH>Device</TH>
              <TH>State</TH>
              <TH>Filed</TH>
              <TH>Expires</TH>
            </TR>
          </THead>
          <TBody>
            {(exceptions.data?.items ?? []).map((ex) => (
              <TR key={ex.id}>
                <TD>
                  <Link to={`/devices/${ex.device_id}`} className="hover:underline">
                    {ex.device_id}
                  </Link>
                </TD>
                <TD>
                  <Badge variant="secondary">{ex.state}</Badge>
                </TD>
                <TD>{new Date(ex.filed_at).toLocaleString()}</TD>
                <TD>{new Date(ex.expires_at).toLocaleString()}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </div>
  );
}
