import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Button } from "./button";

export function Dialog({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className={cn("w-full max-w-lg rounded-xl border border-border bg-card text-card-foreground shadow-xl")}>
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-lg font-semibold">{title}</h2>
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>
        <div className="p-6">{children}</div>
      </div>
    </div>
  );
}
