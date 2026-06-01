import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import type { GardSession } from "@/auth/session";
import { clearSession } from "@/auth/session";
import { useNavigate } from "react-router-dom";

export function Header({ session }: { session: GardSession }) {
  const navigate = useNavigate();

  return (
    <header className="flex items-center justify-between border-b border-border bg-card px-6 py-4 shadow-sm">
      <div className="text-sm text-muted-foreground">Lifecycle governance workspace</div>
      <div className="flex items-center gap-3">
        {session.environment ? <Badge variant="secondary">{session.environment}</Badge> : null}
        <span className="text-sm font-medium text-foreground">{session.subject}</span>
        <div className="flex gap-1">
          {session.roles.map((r) => (
            <Badge key={r} variant="secondary">
              {r}
            </Badge>
          ))}
        </div>
        <ThemeToggle />
        <Button
          variant="outline"
          onClick={() => {
            clearSession();
            navigate("/sign-in");
          }}
        >
          Sign out
        </Button>
      </div>
    </header>
  );
}
