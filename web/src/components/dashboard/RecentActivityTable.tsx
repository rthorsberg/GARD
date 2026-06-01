import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, THead, TH, TR } from "@/components/ui/table";
import type { AuditEvent } from "@/api/types";

export function RecentActivityTable({ items }: { items: AuditEvent[] }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Recent activity</CardTitle>
        <Link to="/audit" className="text-sm font-medium text-muted-foreground hover:underline">
          View all
        </Link>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No recent audit events.</p>
        ) : (
          <Table>
            <THead>
              <TR>
                <TH>Time</TH>
                <TH>Actor</TH>
                <TH>Action</TH>
                <TH>Result</TH>
              </TR>
            </THead>
            <TBody>
              {items.map((e) => (
                <TR key={e.id}>
                  <TD>{new Date(e.timestamp).toLocaleString()}</TD>
                  <TD>{e.actor}</TD>
                  <TD>{e.action}</TD>
                  <TD>
                    <Badge variant={e.result === "success" ? "success" : "secondary"}>{e.result}</Badge>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
