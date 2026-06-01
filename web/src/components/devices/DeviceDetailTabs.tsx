import { useState } from "react";
import { useSession } from "@/hooks/useSession";
import { useDeviceDetail, useDeviceCompliance, useDeviceReadiness } from "@/api/hooks/useDeviceDetail";
import { displayModel, displayPlatform, displayVendor } from "@/lib/device-display";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PostureBadge } from "@/components/ui/posture-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { DeviceEmptyState } from "@/components/actions/ActionResultPanel";
import type { ComplianceEnvelope, DeviceFacts, ReadinessEnvelope } from "@/api/types";

export function DeviceOverviewTab({ facts }: { facts: DeviceFacts }) {
  return (
    <dl className="grid gap-3 text-sm md:grid-cols-2">
      <div>
        <dt className="text-muted-foreground">Hostname</dt>
        <dd className="font-medium">{facts.hostname}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">Site / Region</dt>
        <dd>
          {facts.site}
          {facts.region ? ` (${facts.region})` : ""}
        </dd>
      </div>
      <div>
        <dt className="text-muted-foreground">Vendor</dt>
        <dd>{displayVendor(facts)}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">Model</dt>
        <dd>{displayModel(facts)}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">Platform family</dt>
        <dd>{displayPlatform(facts)}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">Role</dt>
        <dd>{facts.role ?? "—"}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">Management IP</dt>
        <dd>{facts.management_ip ?? "—"}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">Serial</dt>
        <dd>{facts.serial_number ?? "—"}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">Source</dt>
        <dd>{facts.source_system}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">Lifecycle state</dt>
        <dd>{facts.lifecycle_state}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground">NetBox linked</dt>
        <dd>{facts.source_system.startsWith("netbox") ? "Yes" : "No"}</dd>
      </div>
    </dl>
  );
}

export function DeviceComplianceTab({ envelope }: { envelope: ComplianceEnvelope }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <PostureBadge state={envelope.state} />
        {envelope.drift_type ? <Badge variant="secondary">{envelope.drift_type}</Badge> : null}
        <span className="text-sm text-muted-foreground">Evaluated {new Date(envelope.evaluated_at).toLocaleString()}</span>
      </div>
      <p>{envelope.summary}</p>
      <dl className="grid gap-2 text-sm md:grid-cols-2">
        <div>
          <dt className="text-muted-foreground">Observed firmware</dt>
          <dd className="font-medium">{envelope.observed_version ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Target version</dt>
          <dd className="font-medium">{envelope.target_version ?? "—"}</dd>
        </div>
      </dl>
      {envelope.reasons.length > 0 ? (
        <div>
          <h3 className="mb-2 text-sm font-semibold">Reasons</h3>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {envelope.reasons.map((r, i) => (
              <li key={i}>
                <span className="font-medium">{r.kind}</span>
                {r.detail ? `: ${r.detail}` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {(envelope.recommended_actions?.length ?? 0) > 0 ? (
        <div>
          <h3 className="mb-2 text-sm font-semibold">Recommended actions</h3>
          <ul className="space-y-2 text-sm">
            {envelope.recommended_actions!.map((a, i) => (
              <li key={i} className="rounded-lg border border-border bg-muted p-3">
                <div className="font-medium">{a.kind}</div>
                {a.detail ? <p className="mt-1 text-muted-foreground">{a.detail}</p> : null}
                {a.requires?.length ? (
                  <p className="mt-1 text-xs text-muted-foreground">Requires: {a.requires.join(", ")}</p>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export function DeviceReadinessTab({ envelope }: { envelope: ReadinessEnvelope }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <PostureBadge state={envelope.state} domain="readiness" />
        <span className="text-sm text-muted-foreground">Evaluated {new Date(envelope.evaluated_at).toLocaleString()}</span>
      </div>
      <p>{envelope.summary}</p>
      <dl className="grid gap-2 text-sm md:grid-cols-2">
        <div>
          <dt className="text-muted-foreground">Observed firmware</dt>
          <dd>{envelope.observed_version ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Target version</dt>
          <dd>{envelope.target_version ?? "—"}</dd>
        </div>
      </dl>
      {envelope.blockers.length > 0 ? (
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {envelope.blockers.map((b, i) => (
            <li key={i}>
              [{b.severity ?? "info"}] {b.detail ?? "blocker"}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function DeviceDetailPage({ deviceId }: { deviceId: string }) {
  const session = useSession();
  const [tab, setTab] = useState("overview");
  const device = useDeviceDetail(session, deviceId);
  const compliance = useDeviceCompliance(session, deviceId);
  const readiness = useDeviceReadiness(session, deviceId);

  if (device.isLoading) return <Skeleton className="h-64" />;
  if (device.isError || !device.data) {
    return <DeviceEmptyState title="Device not found">Check the device ID or your permissions.</DeviceEmptyState>;
  }

  const facts = device.data.facts;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">{facts.hostname}</h1>
        <p className="text-sm text-muted-foreground">
          {displayVendor(facts)} · {displayModel(facts)} · {facts.site}
        </p>
        <p className="text-xs text-muted-foreground">{facts.id}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Lifecycle profile</CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs>
            <TabsList>
              <TabsTrigger active={tab === "overview"} onClick={() => setTab("overview")}>
                Overview
              </TabsTrigger>
              <TabsTrigger active={tab === "compliance"} onClick={() => setTab("compliance")}>
                Compliance
              </TabsTrigger>
              <TabsTrigger active={tab === "readiness"} onClick={() => setTab("readiness")}>
                Readiness
              </TabsTrigger>
            </TabsList>
            <TabsContent>
              {tab === "overview" ? <DeviceOverviewTab facts={facts} /> : null}
              {tab === "compliance" ? (
                compliance.isLoading ? (
                  <Skeleton className="h-24" />
                ) : compliance.isError || !compliance.data ? (
                  <p className="text-sm text-muted-foreground">Not evaluated</p>
                ) : (
                  <DeviceComplianceTab envelope={compliance.data} />
                )
              ) : null}
              {tab === "readiness" ? (
                readiness.isLoading ? (
                  <Skeleton className="h-24" />
                ) : readiness.isError || !readiness.data ? (
                  <p className="text-sm text-muted-foreground">Not evaluated</p>
                ) : (
                  <DeviceReadinessTab envelope={readiness.data} />
                )
              ) : null}
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
