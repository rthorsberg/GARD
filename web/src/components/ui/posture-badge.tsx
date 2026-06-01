import { compliancePosture, readinessPosture, type PostureToken } from "@/lib/posture";
import { Badge } from "./badge";

export function PostureBadge({ state, domain = "compliance" }: { state: string | null | undefined; domain?: "compliance" | "readiness" }) {
  const token: PostureToken =
    domain === "readiness" ? readinessPosture(state) : compliancePosture(state);
  return <Badge variant={token.variant}>{token.label}</Badge>;
}
