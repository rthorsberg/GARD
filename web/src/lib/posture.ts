export type PostureVariant = "success" | "warning" | "destructive" | "secondary";

export interface PostureToken {
  label: string;
  variant: PostureVariant;
}

const COMPLIANCE: Record<string, PostureToken> = {
  compliant: { label: "Compliant", variant: "success" },
  outside_target: { label: "Drifted", variant: "warning" },
  unknown: { label: "Not evaluated", variant: "secondary" },
  classified: { label: "Classified", variant: "secondary" },
  target_defined: { label: "Target defined", variant: "secondary" },
};

const READINESS: Record<string, PostureToken> = {
  ready_for_uplift: { label: "Ready", variant: "success" },
  blocked: { label: "Blocked", variant: "destructive" },
  not_applicable: { label: "N/A", variant: "secondary" },
};

export function compliancePosture(state: string | null | undefined): PostureToken {
  if (!state) {
    return { label: "Not evaluated", variant: "secondary" };
  }
  return COMPLIANCE[state] ?? { label: state, variant: "secondary" };
}

export function readinessPosture(state: string | null | undefined): PostureToken {
  if (!state) {
    return { label: "Not evaluated", variant: "secondary" };
  }
  return READINESS[state] ?? { label: state, variant: "secondary" };
}

export function driftTotal(counts: {
  target_drift: number;
  catalog_drift: number;
  package_drift: number;
  rule_drift: number;
  evidence_drift: number;
  discovery_drift: number;
  exception_drift: number;
}): number {
  return (
    counts.target_drift +
    counts.catalog_drift +
    counts.package_drift +
    counts.rule_drift +
    counts.evidence_drift +
    counts.discovery_drift +
    counts.exception_drift
  );
}
