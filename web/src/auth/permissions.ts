/** Mirror of gard/core/rbac.py — UX gating only; API is authoritative. */

export const Permission = {
  READ_DEVICE: "device.read",
  LIST_DEVICES: "device.list",
  READ_OBSERVATION: "observation.read",
  READ_AUDIT: "audit.read",
  READ_EVIDENCE: "evidence.read",
  READ_RULE: "rule.read",
  IMPORT_DEVICES: "device.import",
  REEVALUATE_OBSERVATION: "observation.reevaluate",
  MANAGE_RULES: "rule.manage",
  CREATE_MANUAL_MAPPING: "observation.manual_map",
  INVOKE_MCP_TOOL: "mcp.tool.invoke",
  MANAGE_TOKENS: "token.manage",
  MANAGE_MCP_TOOLS: "mcp.tool.manage",
  READ_FIRMWARE_CATALOG: "firmware_catalog.read",
  MANAGE_FIRMWARE_CATALOG: "firmware_catalog.manage",
  MANAGE_FIRMWARE_BLOB: "firmware_catalog.blob.manage",
  READ_COMPLIANCE: "compliance.read",
  RUN_COMPLIANCE_EVAL: "compliance.evaluate",
  READ_READINESS: "readiness.read",
  RUN_READINESS_EVAL: "readiness.evaluate",
  READ_UPLIFT: "uplift.read",
  DRAFT_UPLIFT_WAVE: "uplift.wave.draft",
  APPROVE_UPLIFT_WAVE: "uplift.wave.approve",
  MANAGE_EXCEPTION: "uplift.exception.manage",
  APPROVE_EXCEPTION: "uplift.exception.approve",
  READ_NETBOX: "netbox.read",
  SYNC_NETBOX: "netbox.sync",
} as const;

export type PermissionName = (typeof Permission)[keyof typeof Permission];

const ROLE_PERMISSIONS: Record<string, readonly string[]> = {
  viewer: [
    Permission.READ_DEVICE,
    Permission.LIST_DEVICES,
    Permission.READ_OBSERVATION,
    Permission.READ_AUDIT,
    Permission.READ_EVIDENCE,
    Permission.READ_RULE,
    Permission.READ_FIRMWARE_CATALOG,
    Permission.READ_COMPLIANCE,
    Permission.READ_READINESS,
    Permission.READ_UPLIFT,
    Permission.READ_NETBOX,
  ],
  lifecycle_manager: [
    Permission.READ_DEVICE,
    Permission.LIST_DEVICES,
    Permission.READ_OBSERVATION,
    Permission.READ_AUDIT,
    Permission.READ_EVIDENCE,
    Permission.READ_RULE,
    Permission.IMPORT_DEVICES,
    Permission.REEVALUATE_OBSERVATION,
    Permission.MANAGE_RULES,
    Permission.CREATE_MANUAL_MAPPING,
    Permission.READ_FIRMWARE_CATALOG,
    Permission.MANAGE_FIRMWARE_CATALOG,
    Permission.MANAGE_FIRMWARE_BLOB,
    Permission.READ_COMPLIANCE,
    Permission.RUN_COMPLIANCE_EVAL,
    Permission.READ_READINESS,
    Permission.RUN_READINESS_EVAL,
    Permission.READ_UPLIFT,
    Permission.DRAFT_UPLIFT_WAVE,
    Permission.MANAGE_EXCEPTION,
    Permission.READ_NETBOX,
    Permission.SYNC_NETBOX,
  ],
  mcp_client: [
    Permission.READ_DEVICE,
    Permission.LIST_DEVICES,
    Permission.READ_OBSERVATION,
    Permission.READ_RULE,
    Permission.INVOKE_MCP_TOOL,
    Permission.READ_FIRMWARE_CATALOG,
    Permission.READ_COMPLIANCE,
    Permission.READ_READINESS,
    Permission.READ_UPLIFT,
    Permission.READ_NETBOX,
  ],
  system_admin: [
    Permission.READ_DEVICE,
    Permission.LIST_DEVICES,
    Permission.READ_OBSERVATION,
    Permission.READ_AUDIT,
    Permission.READ_EVIDENCE,
    Permission.READ_RULE,
    Permission.IMPORT_DEVICES,
    Permission.REEVALUATE_OBSERVATION,
    Permission.MANAGE_RULES,
    Permission.CREATE_MANUAL_MAPPING,
    Permission.INVOKE_MCP_TOOL,
    Permission.MANAGE_TOKENS,
    Permission.MANAGE_MCP_TOOLS,
    Permission.READ_FIRMWARE_CATALOG,
    Permission.MANAGE_FIRMWARE_CATALOG,
    Permission.MANAGE_FIRMWARE_BLOB,
    Permission.READ_COMPLIANCE,
    Permission.RUN_COMPLIANCE_EVAL,
    Permission.READ_READINESS,
    Permission.RUN_READINESS_EVAL,
    Permission.READ_UPLIFT,
    Permission.DRAFT_UPLIFT_WAVE,
    Permission.APPROVE_UPLIFT_WAVE,
    Permission.MANAGE_EXCEPTION,
    Permission.APPROVE_EXCEPTION,
    Permission.READ_NETBOX,
    Permission.SYNC_NETBOX,
  ],
  change_approver: [
    Permission.READ_DEVICE,
    Permission.LIST_DEVICES,
    Permission.READ_OBSERVATION,
    Permission.READ_AUDIT,
    Permission.READ_EVIDENCE,
    Permission.READ_RULE,
    Permission.READ_FIRMWARE_CATALOG,
    Permission.READ_COMPLIANCE,
    Permission.READ_READINESS,
    Permission.READ_UPLIFT,
    Permission.APPROVE_UPLIFT_WAVE,
    Permission.APPROVE_EXCEPTION,
    Permission.READ_NETBOX,
  ],
};

export function permissionsForRoles(roles: string[]): Set<string> {
  const out = new Set<string>();
  for (const role of roles) {
    for (const p of ROLE_PERMISSIONS[role] ?? []) {
      out.add(p);
    }
  }
  return out;
}

export function hasPermission(roles: string[], permission: string): boolean {
  return permissionsForRoles(roles).has(permission);
}

export function hasAnyPermission(roles: string[], permissions: string[]): boolean {
  const set = permissionsForRoles(roles);
  return permissions.some((p) => set.has(p));
}

/** Exported for contract tests against rbac.py */
export function allRolePermissionKeys(): Record<string, readonly string[]> {
  return ROLE_PERMISSIONS;
}
