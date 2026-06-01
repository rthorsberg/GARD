import { useState, type ReactNode } from "react";
import { useSession } from "@/hooks/useSession";
import {
  useAddUpgradeEdge,
  useCatalogReload,
  useCatalogTargets,
  useCatalogUpgradePaths,
  useCreateNormRule,
  useDbNormalizationRules,
  useRenormalizeEstate,
  useUpsertTarget,
} from "@/api/hooks/useCatalogAdmin";
import { CanAccess } from "@/auth/CanAccess";
import { Permission } from "@/auth/permissions";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TBody, TD, THead, TH, TR } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { ActionResultPanel, type ActionResult } from "@/components/actions/ActionResultPanel";
import { useToast } from "@/hooks/useToast";

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

const inputClass =
  "w-full rounded-lg border border-border bg-input px-3 py-2 text-sm text-foreground shadow-sm focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/30";

export function CatalogPage() {
  const session = useSession();
  const { toast } = useToast();
  const [tab, setTab] = useState("targets");
  const [result, setResult] = useState<ActionResult | null>(null);

  const targets = useCatalogTargets(session);
  const edges = useCatalogUpgradePaths(session);
  const rules = useDbNormalizationRules(session);
  const reload = useCatalogReload(session);
  const upsertTarget = useUpsertTarget(session);
  const addEdge = useAddUpgradeEdge(session);
  const createRule = useCreateNormRule(session);
  const renormalize = useRenormalizeEstate(session);

  const [targetForm, setTargetForm] = useState({
    name: "cisco-ios-isr1121",
    platform_family: "ios",
    target_version: "17.12.4",
    vendor_normalized: "cisco",
    notes: "",
  });

  const [edgeForm, setEdgeForm] = useState({
    platform_family: "ios",
    from_version: "16.9.5",
    to_version: "17.12.4",
    notes: "Lab upgrade hop",
  });

  const [ruleForm, setRuleForm] = useState({
    model_pattern: "(?i)ISR1121",
    vendor_normalized: "cisco",
    platform_family: "ios",
    model_normalized: "ISR1121",
    notes: "ISR1121 normalization",
  });

  async function onReload() {
    try {
      const res = await reload.mutateAsync();
      setResult({
        action: "catalog_reload",
        status: "success",
        summary: "Catalog reloaded",
        counts: {
          firmware_loaded: res.firmware_loaded,
          devices_reevaluated: res.devices_reevaluated,
        },
      });
      toast("Catalog reloaded");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

  async function onSaveTarget() {
    try {
      const res = await upsertTarget.mutateAsync({
        name: targetForm.name,
        platform_family: targetForm.platform_family,
        target_version: targetForm.target_version,
        scope_selector: {
          vendor_normalized: targetForm.vendor_normalized,
          platform_family: targetForm.platform_family,
        },
        notes: targetForm.notes || undefined,
      });
      setResult({
        action: "upsert_target",
        status: "success",
        summary: `Target ${targetForm.name} saved and reloaded`,
        counts: { devices_reevaluated: res.devices_reevaluated },
      });
      toast("Firmware target saved");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

  async function onAddEdge() {
    try {
      await addEdge.mutateAsync(edgeForm);
      toast("Upgrade path edge added");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

  async function onCreateRule() {
    try {
      const res = await createRule.mutateAsync(ruleForm);
      setResult({
        action: "create_rule",
        status: "success",
        summary: `Normalization rule ${(res as { id: string }).id} created`,
      });
      toast("Model mapping rule created — devices re-normalized");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

  async function onRenormalize() {
    try {
      const res = await renormalize.mutateAsync();
      setResult({
        action: "renormalize",
        status: "success",
        summary: "Estate re-normalized",
        counts: { devices_updated: res.devices_updated },
      });
      toast("Devices re-normalized");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Firmware catalog</h1>
          <p className="text-sm text-muted-foreground">
            Define target versions, upgrade paths, and model normalization — no manual YAML editing
          </p>
        </div>
        <CanAccess roles={session.roles} permission={Permission.MANAGE_FIRMWARE_CATALOG}>
          <Button onClick={() => void onReload()} disabled={reload.isPending}>
            {reload.isPending ? "Reloading…" : "Reload catalog"}
          </Button>
        </CanAccess>
      </div>

      <Tabs>
        <TabsList>
          <TabsTrigger active={tab === "targets"} onClick={() => setTab("targets")}>
            Targets
          </TabsTrigger>
          <TabsTrigger active={tab === "paths"} onClick={() => setTab("paths")}>
            Upgrade paths
          </TabsTrigger>
          <TabsTrigger active={tab === "models"} onClick={() => setTab("models")}>
            Model rules
          </TabsTrigger>
        </TabsList>
        <TabsContent>
          {tab === "targets" ? (
            <div className="grid gap-6 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle>Create / update target</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <Field label="Name (slug)">
                    <input
                      className={inputClass}
                      value={targetForm.name}
                      onChange={(e) => setTargetForm({ ...targetForm, name: e.target.value })}
                    />
                  </Field>
                  <Field label="Platform family">
                    <input
                      className={inputClass}
                      value={targetForm.platform_family}
                      onChange={(e) => setTargetForm({ ...targetForm, platform_family: e.target.value })}
                    />
                  </Field>
                  <Field label="Target version">
                    <input
                      className={inputClass}
                      value={targetForm.target_version}
                      onChange={(e) => setTargetForm({ ...targetForm, target_version: e.target.value })}
                    />
                  </Field>
                  <Field label="Scope: vendor_normalized">
                    <input
                      className={inputClass}
                      value={targetForm.vendor_normalized}
                      onChange={(e) => setTargetForm({ ...targetForm, vendor_normalized: e.target.value })}
                    />
                  </Field>
                  <CanAccess roles={session.roles} permission={Permission.MANAGE_FIRMWARE_CATALOG}>
                    <Button onClick={() => void onSaveTarget()} disabled={upsertTarget.isPending}>
                      Save target
                    </Button>
                  </CanAccess>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Live targets</CardTitle>
                </CardHeader>
                <CardContent>
                  {targets.isLoading ? (
                    <Skeleton className="h-32" />
                  ) : (
                    <Table>
                      <THead>
                        <TR>
                          <TH>Name</TH>
                          <TH>Platform</TH>
                          <TH>Version</TH>
                        </TR>
                      </THead>
                      <TBody>
                        {(targets.data?.items ?? []).map((t) => (
                          <TR key={t.id}>
                            <TD>{t.name}</TD>
                            <TD>{t.platform_family}</TD>
                            <TD>{t.target_version}</TD>
                          </TR>
                        ))}
                      </TBody>
                    </Table>
                  )}
                </CardContent>
              </Card>
            </div>
          ) : null}

          {tab === "paths" ? (
            <div className="grid gap-6 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle>Add upgrade edge</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <Field label="Platform family">
                    <input
                      className={inputClass}
                      value={edgeForm.platform_family}
                      onChange={(e) => setEdgeForm({ ...edgeForm, platform_family: e.target.value })}
                    />
                  </Field>
                  <Field label="From version">
                    <input
                      className={inputClass}
                      value={edgeForm.from_version}
                      onChange={(e) => setEdgeForm({ ...edgeForm, from_version: e.target.value })}
                    />
                  </Field>
                  <Field label="To version">
                    <input
                      className={inputClass}
                      value={edgeForm.to_version}
                      onChange={(e) => setEdgeForm({ ...edgeForm, to_version: e.target.value })}
                    />
                  </Field>
                  <CanAccess roles={session.roles} permission={Permission.MANAGE_FIRMWARE_CATALOG}>
                    <Button onClick={() => void onAddEdge()} disabled={addEdge.isPending}>
                      Add edge
                    </Button>
                  </CanAccess>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Declared edges</CardTitle>
                </CardHeader>
                <CardContent>
                  {edges.isLoading ? (
                    <Skeleton className="h-32" />
                  ) : (
                    <Table>
                      <THead>
                        <TR>
                          <TH>Platform</TH>
                          <TH>From</TH>
                          <TH>To</TH>
                        </TR>
                      </THead>
                      <TBody>
                        {(edges.data?.items ?? []).map((e) => (
                          <TR key={e.id}>
                            <TD>{e.platform_family}</TD>
                            <TD>{e.from_version}</TD>
                            <TD>{e.to_version}</TD>
                          </TR>
                        ))}
                      </TBody>
                    </Table>
                  )}
                </CardContent>
              </Card>
            </div>
          ) : null}

          {tab === "models" ? (
            <div className="grid gap-6 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle>Map model → vendor / platform</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm text-muted-foreground">
                    Fixes empty vendor/platform on imported devices so firmware targets can match.
                  </p>
                  <Field label="Model regex">
                    <input
                      className={inputClass}
                      value={ruleForm.model_pattern}
                      onChange={(e) => setRuleForm({ ...ruleForm, model_pattern: e.target.value })}
                    />
                  </Field>
                  <Field label="vendor_normalized">
                    <input
                      className={inputClass}
                      value={ruleForm.vendor_normalized}
                      onChange={(e) => setRuleForm({ ...ruleForm, vendor_normalized: e.target.value })}
                    />
                  </Field>
                  <Field label="platform_family">
                    <input
                      className={inputClass}
                      value={ruleForm.platform_family}
                      onChange={(e) => setRuleForm({ ...ruleForm, platform_family: e.target.value })}
                    />
                  </Field>
                  <Field label="model_normalized">
                    <input
                      className={inputClass}
                      value={ruleForm.model_normalized}
                      onChange={(e) => setRuleForm({ ...ruleForm, model_normalized: e.target.value })}
                    />
                  </Field>
                  <CanAccess roles={session.roles} permission={Permission.MANAGE_RULES}>
                    <div className="flex gap-2">
                      <Button onClick={() => void onCreateRule()} disabled={createRule.isPending}>
                        Save rule
                      </Button>
                      <Button variant="outline" onClick={() => void onRenormalize()} disabled={renormalize.isPending}>
                        Re-normalize all
                      </Button>
                    </div>
                  </CanAccess>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>UI-created rules</CardTitle>
                </CardHeader>
                <CardContent>
                  {rules.isLoading ? (
                    <Skeleton className="h-32" />
                  ) : rules.isError ? (
                    <p className="text-sm text-muted-foreground">Catalog editor API unavailable in this environment.</p>
                  ) : (
                    <Table>
                      <THead>
                        <TR>
                          <TH>ID</TH>
                          <TH>Match</TH>
                          <TH>Output</TH>
                        </TR>
                      </THead>
                      <TBody>
                        {(rules.data?.items ?? []).map((r) => (
                          <TR key={r.id}>
                            <TD className="text-xs">{r.id}</TD>
                            <TD className="text-xs">{JSON.stringify(r.match)}</TD>
                            <TD className="text-xs">{JSON.stringify(r.output)}</TD>
                          </TR>
                        ))}
                      </TBody>
                    </Table>
                  )}
                </CardContent>
              </Card>
            </div>
          ) : null}
        </TabsContent>
      </Tabs>

      <ActionResultPanel result={result} />
    </div>
  );
}
