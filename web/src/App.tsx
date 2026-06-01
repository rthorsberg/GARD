import { Navigate, Route, Routes } from "react-router-dom";
import { AuthGuard } from "@/auth/AuthGuard";
import { AppShell } from "@/components/layout/AppShell";
import { loadSession } from "@/auth/session";
import { SignInPage } from "@/routes/sign-in";
import { DashboardPage } from "@/routes/dashboard";
import { DevicesListPage } from "@/routes/devices/index";
import { DeviceDetailRoute } from "@/routes/devices/detail";
import { CompliancePage } from "@/routes/compliance";
import { CatalogPage } from "@/routes/catalog";
import { ReadinessPage } from "@/routes/readiness";
import { NetboxPage } from "@/routes/netbox";
import { UpliftListPage } from "@/routes/uplift/index";
import { UpliftWaveDetailPage } from "@/routes/uplift/wave-detail";
import { UpliftExceptionsPage } from "@/routes/uplift/exceptions";
import { AuditPage } from "@/routes/audit";

function RootRedirect() {
  const session = loadSession();
  return <Navigate to={session ? "/dashboard" : "/sign-in"} replace />;
}

export function App() {
  return (
    <Routes>
      <Route path="/sign-in" element={<SignInPage />} />
      <Route element={<AuthGuard />}>
        <Route element={<AppShell />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/devices" element={<DevicesListPage />} />
          <Route path="/devices/:deviceId" element={<DeviceDetailRoute />} />
          <Route path="/compliance" element={<CompliancePage />} />
          <Route path="/catalog" element={<CatalogPage />} />
          <Route path="/readiness" element={<ReadinessPage />} />
          <Route path="/netbox" element={<NetboxPage />} />
          <Route path="/uplift" element={<UpliftListPage />} />
          <Route path="/uplift/waves/:waveId" element={<UpliftWaveDetailPage />} />
          <Route path="/uplift/exceptions" element={<UpliftExceptionsPage />} />
          <Route path="/audit" element={<AuditPage />} />
        </Route>
      </Route>
      <Route path="/" element={<RootRedirect />} />
      <Route path="*" element={<RootRedirect />} />
    </Routes>
  );
}
