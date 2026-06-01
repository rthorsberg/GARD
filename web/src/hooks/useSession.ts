import { useOutletContext } from "react-router-dom";
import type { GardSession } from "@/auth/session";

export function useSession(): GardSession {
  return useOutletContext<GardSession>();
}
