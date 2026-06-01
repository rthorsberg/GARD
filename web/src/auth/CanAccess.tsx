import type { ReactNode } from "react";
import { hasPermission } from "./permissions";

interface CanAccessProps {
  roles: string[];
  permission: string;
  children: ReactNode;
  fallback?: ReactNode;
}

export function CanAccess({ roles, permission, children, fallback = null }: CanAccessProps) {
  if (!hasPermission(roles, permission)) {
    return <>{fallback}</>;
  }
  return <>{children}</>;
}
