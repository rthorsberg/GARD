import { NavLink } from "react-router-dom";
import { LayoutDashboard, Server, ShieldCheck, Activity, Waves, Network, ScrollText, BookOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import { hasAnyPermission, Permission } from "@/auth/permissions";

const nav = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, perms: [Permission.READ_COMPLIANCE, Permission.LIST_DEVICES] },
  { to: "/devices", label: "Devices", icon: Server, perms: [Permission.LIST_DEVICES] },
  { to: "/compliance", label: "Compliance", icon: ShieldCheck, perms: [Permission.READ_COMPLIANCE] },
  { to: "/catalog", label: "Catalog", icon: BookOpen, perms: [Permission.READ_FIRMWARE_CATALOG] },
  { to: "/readiness", label: "Readiness", icon: Activity, perms: [Permission.READ_READINESS] },
  { to: "/uplift", label: "Uplift", icon: Waves, perms: [Permission.READ_UPLIFT] },
  { to: "/netbox", label: "NetBox", icon: Network, perms: [Permission.READ_NETBOX] },
  { to: "/audit", label: "Audit", icon: ScrollText, perms: [Permission.READ_AUDIT] },
];

export function Sidebar({ roles }: { roles: string[] }) {
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-sidebar-border bg-sidebar">
      <div className="border-b border-sidebar-border px-6 py-5">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">GARD</div>
        <div className="text-lg font-bold text-foreground">Operator Portal</div>
      </div>
      <nav className="flex flex-1 flex-col gap-1 p-3">
        {nav
          .filter((item) => hasAnyPermission(roles, item.perms))
          .map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-sidebar-active text-sidebar-active-foreground shadow-sm [&_svg]:text-sidebar-active-foreground"
                    : "text-sidebar-foreground hover:bg-muted hover:text-foreground",
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden />
              <span>{label}</span>
            </NavLink>
          ))}
      </nav>
    </aside>
  );
}
