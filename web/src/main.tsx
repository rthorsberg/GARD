import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "@/components/ui/toast-provider";
import { initTheme } from "@/hooks/useTheme";
import { App } from "./App";
import "./index.css";

initTheme();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (count, error) => {
        const status = (error as { status?: number }).status;
        if (status === 401 || status === 403) return false;
        if (status != null && status >= 502) return count < 2;
        return count < 1;
      },
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
);
