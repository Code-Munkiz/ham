import * as React from "react";
import type { VercelHookMapping } from "@/lib/ham/api";
import type {
  CloudMissionHandling,
  ManagedDeployHandoffState,
  ManagedDeployReadiness,
  ManagedMissionReview,
  ManagedMissionSnapshot,
} from "@/lib/ham/types";

export type ManagedCloudAgentContextValue = {
  activeCloudAgentId: string | null;
  cloudMissionHandling: CloudMissionHandling;
  lastSnapshot: ManagedMissionSnapshot | null;
  lastReview: ManagedMissionReview | null;
  lastDeployReadiness: ManagedDeployReadiness | null;
  lastUpdated: number | null;
  /** Managed poll: last request error, if any */
  pollError: string | null;
  /** Managed poll: in-flight */
  pollPending: boolean;
  refresh: () => void;
  /** Server has a resolvable deploy hook for this agent (or global); null while loading */
  deployHookConfigured: boolean | null;
  /** Per-repo / global deploy hook mapping (no secrets) */
  deployHookVercelMapping: VercelHookMapping | null;
  /** User handoff result overlay; combined with readiness in the panel */
  deployHandoffState: ManagedDeployHandoffState;
  deployHandoffMessage: string | null;
  triggerManagedDeploy: (() => Promise<void>) | null;
};

const ManagedCloudAgentContext = React.createContext<ManagedCloudAgentContextValue | null>(null);

export function ManagedCloudAgentProvider({
  value,
  children,
}: {
  value: ManagedCloudAgentContextValue;
  children: React.ReactNode;
}) {
  return <ManagedCloudAgentContext.Provider value={value}>{children}</ManagedCloudAgentContext.Provider>;
}

export function useManagedCloudAgentContext(): ManagedCloudAgentContextValue {
  const v = React.useContext(ManagedCloudAgentContext);
  if (!v) {
    throw new Error("useManagedCloudAgentContext must be used under ManagedCloudAgentProvider");
  }
  return v;
}
