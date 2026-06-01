import { createContext } from "react";

export interface ToastContextValue {
  toast: (message: string, variant?: "default" | "error") => void;
}

export const ToastContext = createContext<ToastContextValue | null>(null);
