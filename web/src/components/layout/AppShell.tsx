import { Outlet } from "react-router-dom";
import { useSession } from "@/hooks/useSession";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";

export function AppShell() {
  const session = useSession();

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <Sidebar roles={session.roles} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header session={session} />
        <main className="flex-1 overflow-auto p-6">
          <Outlet context={session} />
        </main>
      </div>
    </div>
  );
}
