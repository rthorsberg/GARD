import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { healthCheck } from "@/api/client";
import { saveSession, sessionFromToken } from "@/auth/session";

const fieldClass =
  "w-full rounded-lg border border-border bg-input px-3 py-2 text-sm text-foreground shadow-sm focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/30";

export function SignInPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/dashboard";

  const [apiBaseUrl, setApiBaseUrl] = useState("");
  const [token, setToken] = useState("");
  const [environment, setEnvironment] = useState("lab");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const session = sessionFromToken(token, apiBaseUrl, environment);
      const ok = await healthCheck(session);
      if (!ok) {
        setError("Could not reach GARD API. Check base URL and that the service is running.");
        return;
      }
      saveSession(session);
      navigate(from, { replace: true });
    } catch {
      setError("Sign-in failed. Check your token and API URL.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="absolute right-6 top-6">
        <ThemeToggle />
      </div>
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle>GARD Operator Portal</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={onSubmit}>
            <label className="block space-y-1 text-sm">
              <span className="font-medium text-foreground">API base URL</span>
              <input
                className={fieldClass}
                placeholder="Leave empty for same-origin proxy"
                value={apiBaseUrl}
                onChange={(e) => setApiBaseUrl(e.target.value)}
              />
            </label>
            <label className="block space-y-1 text-sm">
              <span className="font-medium text-foreground">Environment label</span>
              <input className={fieldClass} value={environment} onChange={(e) => setEnvironment(e.target.value)} />
            </label>
            <label className="block space-y-1 text-sm">
              <span className="font-medium text-foreground">JWT bearer token</span>
              <textarea
                className={`${fieldClass} h-28 font-mono text-xs`}
                required
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
            </label>
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
            <Button type="submit" disabled={loading} className="w-full">
              {loading ? "Connecting…" : "Sign in"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
