import { describe, expect, it } from "vitest";
import { allRolePermissionKeys, Permission } from "@/auth/permissions";

describe("permissions mirror", () => {
  it("includes core viewer read permissions", () => {
    const viewer = allRolePermissionKeys().viewer;
    expect(viewer).toContain(Permission.READ_COMPLIANCE);
    expect(viewer).toContain(Permission.READ_NETBOX);
  });

  it("grants sync to lifecycle_manager", () => {
    expect(allRolePermissionKeys().lifecycle_manager).toContain(Permission.SYNC_NETBOX);
  });
});
