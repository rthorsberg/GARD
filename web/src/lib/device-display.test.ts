import { describe, expect, it } from "vitest";
import { displayPlatform, displayVendor } from "@/lib/device-display";

describe("device display", () => {
  it("falls back to vendor_raw when normalized fields are missing", () => {
    expect(displayVendor({ vendor_normalized: null, vendor_raw: "Cisco Systems" })).toBe("Cisco Systems");
  });

  it("infers platform family from vendor when platform_family is null", () => {
    expect(
      displayPlatform({
        platform_family: null,
        vendor_normalized: null,
        vendor_raw: "Juniper Networks",
      }),
    ).toBe("junos");
  });
});
