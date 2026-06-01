import { useState } from "react";
import { useSession } from "@/hooks/useSession";
import { useImportCsv } from "@/api/hooks/useImportCsv";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ActionResultPanel, type ActionResult } from "@/components/actions/ActionResultPanel";
import { useToast } from "@/hooks/useToast";

export function ImportCsvDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const session = useSession();
  const mutation = useImportCsv(session);
  const { toast } = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ActionResult | null>(null);

  async function onImport() {
    if (!file) return;
    try {
      const outcome = await mutation.mutateAsync(file);
      const { summary, compliance, readiness, evaluationWarning } = outcome;
      setResult({
        action: "import",
        status: evaluationWarning ? "partial" : "success",
        summary: evaluationWarning
          ? "Import completed; evaluation failed"
          : "Import completed",
        counts: {
          rows_total: summary.totals.rows_total,
          rows_accepted: summary.totals.rows_accepted,
          devices_created: summary.totals.devices_created,
          devices_updated: summary.totals.devices_updated,
          compliance_evaluated: compliance?.evaluated_count,
          readiness_evaluated: readiness?.evaluated_count,
        },
        errors: evaluationWarning ? [evaluationWarning] : undefined,
      });
      if (evaluationWarning) {
        toast("Import succeeded but evaluation failed", "error");
      } else {
        toast("Import completed — devices evaluated for compliance");
      }
    } catch (e) {
      const msg = (e as Error).message;
      setResult({ action: "import", status: "failed", summary: "Import failed", errors: [msg] });
      toast(msg, "error");
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Import devices (CSV)">
      <div className="space-y-4">
        <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <div className="flex gap-2">
          <Button disabled={!file || mutation.isPending} onClick={() => void onImport()}>
            {mutation.isPending ? "Importing…" : "Upload"}
          </Button>
        </div>
        <ActionResultPanel result={result} />
      </div>
    </Dialog>
  );
}
