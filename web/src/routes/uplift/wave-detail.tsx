import { Link, useParams } from "react-router-dom";
import { useSession } from "@/hooks/useSession";
import { useUpliftWaveDetail } from "@/api/hooks/useUpliftWaves";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiRequest } from "@/api/client";
import { CanAccess } from "@/auth/CanAccess";
import { Permission } from "@/auth/permissions";
import { Button } from "@/components/ui/button";
import { Table, TBody, TD, THead, TH, TR } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/useToast";

export function UpliftWaveDetailPage() {
  const { waveId = "" } = useParams();
  const session = useSession();
  const wave = useUpliftWaveDetail(session, waveId);
  const qc = useQueryClient();
  const { toast } = useToast();

  const submit = useMutation({
    mutationFn: () => apiRequest(session, `/api/v1/uplift/waves/${waveId}/submit`, { method: "POST", body: {} }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["uplift"] });
      toast("Wave submitted");
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  if (wave.isLoading) return <Skeleton className="h-64" />;
  if (!wave.data) return <p>Wave not found</p>;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <Link to="/uplift" className="text-sm text-muted-foreground hover:underline">
            ← Waves
          </Link>
          <h1 className="text-2xl font-bold">{wave.data.name}</h1>
          <p className="text-sm text-muted-foreground">
            {wave.data.state} · target {wave.data.target_version}
          </p>
        </div>
        <CanAccess roles={session.roles} permission={Permission.DRAFT_UPLIFT_WAVE}>
          {wave.data.state === "draft" ? (
            <Button onClick={() => void submit.mutate()} disabled={submit.isPending}>
              Submit wave
            </Button>
          ) : null}
        </CanAccess>
      </div>

      <Table>
        <THead>
          <TR>
            <TH>#</TH>
            <TH>Hostname</TH>
            <TH>Observed</TH>
            <TH>Target snapshot</TH>
          </TR>
        </THead>
        <TBody>
          {wave.data.devices.map((d) => (
            <TR key={d.device_id}>
              <TD>{d.position}</TD>
              <TD>
                <Link to={`/devices/${d.device_id}`} className="hover:underline">
                  {d.hostname}
                </Link>
              </TD>
              <TD>{d.snapshot_observed_version ?? "—"}</TD>
              <TD>{d.snapshot_target_version ?? "—"}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </div>
  );
}
