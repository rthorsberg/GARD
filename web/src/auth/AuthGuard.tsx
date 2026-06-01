import { Navigate, Outlet, useLocation } from "react-router-dom";
import { loadSession } from "./session";

export function AuthGuard() {
  const location = useLocation();
  const session = loadSession();
  if (!session) {
    return <Navigate to="/sign-in" replace state={{ from: location.pathname }} />;
  }
  return <Outlet context={session} />;
}
