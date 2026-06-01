import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const COLORS = ["#16a34a", "#ca8a04", "#71717a"];

interface PostureChartProps {
  compliant: number;
  drifted: number;
  unknown: number;
}

export function PostureChart({ compliant, drifted, unknown }: PostureChartProps) {
  const data = [
    { name: "Compliant", value: compliant },
    { name: "Drifted", value: drifted },
    { name: "Not evaluated", value: unknown },
  ].filter((d) => d.value > 0);

  if (data.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Compliance posture</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">No evaluation data yet.</CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Compliance posture</CardTitle>
      </CardHeader>
      <CardContent className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="value" nameKey="name" innerRadius={50} outerRadius={80}>
              {data.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
