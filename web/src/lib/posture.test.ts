import { describe, expect, it } from "vitest";
import { compliancePosture } from "@/lib/posture";

describe("compliancePosture", () => {
  it("shows not evaluated for missing state", () => {
    expect(compliancePosture(null).label).toBe("Not evaluated");
  });

  it("maps outside_target to Drifted", () => {
    expect(compliancePosture("outside_target").label).toBe("Drifted");
  });
});
