import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Tabs({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("space-y-4", className)}>{children}</div>;
}

export function TabsList({ children }: { children: ReactNode }) {
  return <div className="flex gap-2 border-b border-border">{children}</div>;
}

export function TabsTrigger({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "border-b-2 px-4 py-2 text-sm font-medium transition-colors",
        active
          ? "border-primary text-foreground"
          : "border-transparent text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

export function TabsContent({ children }: { children: ReactNode }) {
  return <div>{children}</div>;
}
