import { cn } from "@/lib/utils";
import type { PostureVariant } from "@/lib/posture";

const styles: Record<PostureVariant, string> = {
  success:
    "bg-green-100 text-green-800 border-green-300 dark:bg-green-950 dark:text-green-300 dark:border-green-800",
  warning:
    "bg-amber-100 text-amber-900 border-amber-300 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800",
  destructive: "bg-red-100 text-red-800 border-red-300 dark:bg-red-950 dark:text-red-300 dark:border-red-800",
  secondary: "bg-muted text-muted-foreground border-border",
};

export function Badge({
  children,
  variant = "secondary",
  className,
}: {
  children: React.ReactNode;
  variant?: PostureVariant | "default";
  className?: string;
}) {
  const v = variant === "default" ? "secondary" : variant;
  return (
    <span className={cn("inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium", styles[v], className)}>
      {children}
    </span>
  );
}
