import { useSession } from "@/hooks/useSession";
import { useEvidenceList } from "@/api/hooks/useEvidenceList";
import { Dialog } from "@/components/ui/dialog";
import { Table, TBody, TD, THead, TH, TR } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";

export function EvidenceDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const session = useSession();
  const evidence = useEvidenceList(session);

  return (
    <Dialog open={open} onClose={onClose} title="Evidence artifacts">
      {evidence.isLoading ? (
        <Skeleton className="h-32" />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Kind</TH>
              <TH>Created</TH>
              <TH>Correlation</TH>
            </TR>
          </THead>
          <TBody>
            {(evidence.data?.items ?? []).map((item) => (
              <TR key={item.id}>
                <TD>{item.evidence_type}</TD>
                <TD>{new Date(item.timestamp).toLocaleString()}</TD>
                <TD className="font-mono text-xs">{item.subject_type}/{item.subject_id}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </Dialog>
  );
}
