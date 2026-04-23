import * as React from "react";
import type { CloudMissionHandling, ManagedMissionSnapshot } from "@/lib/ham/types";

export type ManagedCloudAgentContextValue = {
  activeCloudAgentId: string | null;
  cloudMissionHandling: CloudMissionHandling;
  lastSnapshot: ManagedMissionSnapshot | null;
  lastUpdated: number | null;
  refresh: () => void;
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
