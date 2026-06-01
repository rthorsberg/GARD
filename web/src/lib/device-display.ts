import type { ComplianceDeviceRow, DeviceFacts } from "@/api/types";

export function displayVendor(facts: Pick<DeviceFacts, "vendor_normalized" | "vendor_raw">): string {
  return facts.vendor_normalized ?? facts.vendor_raw ?? "—";
}

export function displayModel(facts: Pick<DeviceFacts, "model_normalized" | "model_raw">): string {
  return facts.model_normalized ?? facts.model_raw ?? "—";
}

export function displayPlatform(
  facts: Pick<DeviceFacts, "platform_family" | "vendor_normalized" | "vendor_raw">,
): string {
  if (facts.platform_family) return facts.platform_family;
  if (facts.vendor_normalized) return facts.vendor_normalized;
  const raw = facts.vendor_raw ?? "";
  if (/cisco/i.test(raw)) return "ios";
  if (/juniper/i.test(raw)) return "junos";
  if (/nokia|alcatel/i.test(raw)) return "sros";
  if (/arista/i.test(raw)) return "eos";
  return raw || "—";
}

export type EnrichedDeviceRow = ComplianceDeviceRow & {
  vendor: string;
  model: string;
  platform: string;
};

export function enrichComplianceRow(
  row: ComplianceDeviceRow,
  facts?: DeviceFacts,
): EnrichedDeviceRow {
  const vendor = facts ? displayVendor(facts) : "—";
  const model = facts ? displayModel(facts) : "—";
  const platform = facts ? displayPlatform(facts) : row.platform_family ?? "—";
  return { ...row, vendor, model, platform };
}
