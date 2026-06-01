import { useCallback, useMemo, useState, type ReactNode } from "react";
import { ToastContext } from "./toast-context";

interface Toast {
  id: string;
  message: string;
  variant?: "default" | "error";
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);

  const toast = useCallback((message: string, variant: "default" | "error" = "default") => {
    const id = crypto.randomUUID();
    setItems((prev) => [...prev, { id, message, variant }]);
    setTimeout(() => setItems((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
        {items.map((t) => (
          <div
            key={t.id}
            className={
              t.variant === "error"
                ? "rounded-lg border border-red-700 bg-destructive px-4 py-2 text-sm text-white shadow-lg"
                : "rounded-lg border border-border bg-card px-4 py-2 text-sm text-foreground shadow-lg"
            }
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
