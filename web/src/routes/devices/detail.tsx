import { useParams } from "react-router-dom";
import { DeviceDetailPage } from "@/components/devices/DeviceDetailTabs";

export function DeviceDetailRoute() {
  const { deviceId = "" } = useParams();
  return <DeviceDetailPage deviceId={deviceId} />;
}
