import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ComplianceDeviceRow } from "@/api/types";

export function DevicesBySiteChart({ devices }: { devices: ComplianceDeviceRow[] }) {
  const counts = new Map<string, number>();
  for (const d of devices) {
    const site = d.site || "Unknown";
    counts.set(site, (counts.get(site) ?? 0) + 1);
  }
  const data = [...counts.entries()]
    .map(([site, count]) => ({ site, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 8);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Devices by site</CardTitle>
      </CardHeader>
      <CardContent className="h-64">
        {data.length === 0 ? (
          <div className="text-sm text-muted-foreground">No devices in current sample.</div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ left: 24 }}>
              <XAxis type="number" allowDecimals={false} />
              <YAxis type="category" dataKey="site" width={80} tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="count" fill="#18181b" radius={4} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
