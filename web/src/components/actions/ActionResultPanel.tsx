import type { ReactNode } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface ActionResult {
  action: string;
  status: "success" | "partial" | "failed";
  summary: string;
  counts?: Record<string, number>;
  errors?: string[];
}

export function ActionResultPanel({ result }: { result: ActionResult | null }) {
  if (!result) return null;

  const tone = cn(
    result.status === "success" &&
      "border-green-300 bg-green-50 dark:border-green-800 dark:bg-green-950/50",
    result.status === "partial" &&
      "border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/50",
    result.status === "failed" && "border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-950/50",
  );

  return (
    <Card className={tone}>
      <CardContent className="space-y-2 pt-6">
        <div className="font-semibold text-foreground">{result.summary}</div>
        {result.counts ? (
          <dl className="grid grid-cols-2 gap-2 text-sm md:grid-cols-4">
            {Object.entries(result.counts).map(([k, v]) => (
              <div key={k}>
                <dt className="text-muted-foreground">{k}</dt>
                <dd className="font-medium text-foreground">{v}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        {result.errors?.map((e) => (
          <p key={e} className="text-sm text-destructive">
            {e}
          </p>
        ))}
      </CardContent>
    </Card>
  );
}

export function DeviceEmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <Card>
      <CardContent className="py-12 text-center">
        <h3 className="text-lg font-semibold text-foreground">{title}</h3>
        {children ? <div className="mt-2 text-sm text-muted-foreground">{children}</div> : null}
      </CardContent>
    </Card>
  );
}
