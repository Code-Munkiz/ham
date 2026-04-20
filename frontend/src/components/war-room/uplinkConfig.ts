/**
 * Formal uplink → tabs mapping for War Room / split execution surface.
 * @see docs/WAR_ROOM_UPLINK_TABBED_SPEC.md
 */
import type { UplinkId } from "@/components/chat/ChatComposerStrip";

export type CloudAgentTabId = "tracker" | "transcript" | "artifacts" | "browser" | "overview";
export type FactoryAiTabId = "swarm" | "workers" | "queue" | "browser";
export type ElizaOsTabId = "thought_stream" | "context" | "trace" | "browser";

export type WarRoomTabId = CloudAgentTabId | FactoryAiTabId | ElizaOsTabId;

export type WarRoomTabDef = {
  id: WarRoomTabId;
  label: string;
};

const CLOUD_AGENT_TABS: WarRoomTabDef[] = [
  { id: "tracker", label: "Tracker" },
  { id: "transcript", label: "Transcript" },
  { id: "artifacts", label: "Artifacts" },
  { id: "browser", label: "Browser" },
  { id: "overview", label: "Overview" },
];

const FACTORY_AI_TABS: WarRoomTabDef[] = [
  { id: "swarm", label: "Swarm" },
  { id: "workers", label: "Workers" },
  { id: "queue", label: "Queue" },
  { id: "browser", label: "Browser" },
];

const ELIZA_OS_TABS: WarRoomTabDef[] = [
  { id: "thought_stream", label: "Thought Stream" },
  { id: "context", label: "Context" },
  { id: "trace", label: "Trace" },
  { id: "browser", label: "Browser" },
];

const DEFAULT_TAB: Record<UplinkId, WarRoomTabId> = {
  cloud_agent: "tracker",
  factory_ai: "swarm",
  eliza_os: "thought_stream",
};

export function getWarRoomTabs(uplink: UplinkId): WarRoomTabDef[] {
  if (uplink === "cloud_agent") return CLOUD_AGENT_TABS;
  if (uplink === "factory_ai") return FACTORY_AI_TABS;
  return ELIZA_OS_TABS;
}

export function getDefaultWarRoomTab(uplink: UplinkId): WarRoomTabId {
  return DEFAULT_TAB[uplink];
}
