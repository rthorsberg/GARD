import { Link } from "react-router-dom";
import { Card, CardContent } from "@/components/ui/card";

interface KpiCardProps {
  title: string;
  value: string | number;
  hint?: string;
  href?: string;
}

export function KpiCard({ title, value, hint, href }: KpiCardProps) {
  const content = (
    <Card className={href ? "transition hover:shadow-md" : undefined}>
      <CardContent className="space-y-2 pt-6">
        <div className="text-sm text-muted-foreground">{title}</div>
        <div className="text-3xl font-bold tracking-tight text-foreground">{value}</div>
        {hint ? <div className="text-xs text-muted-foreground">{hint}</div> : null}
        {href ? <div className="text-xs font-medium text-muted-foreground">View more →</div> : null}
      </CardContent>
    </Card>
  );

  if (href) {
    return <Link to={href}>{content}</Link>;
  }
  return content;
}
