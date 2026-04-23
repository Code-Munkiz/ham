import type { UplinkId } from "@/components/chat/ChatComposerStrip";
import type { CloudMissionHandling, ManagedMissionSnapshot } from "@/lib/ham/types";

import { CloudAgentPanel } from "./CloudAgentPanel";
import { ElizaOsPanel } from "./ElizaOsPanel";
import { FactoryAIPanel } from "./FactoryAIPanel";
import { BrowserTabPanel } from "./BrowserTabPanel";
import type { WarRoomTabId } from "./uplinkConfig";

export interface WarRoomPaneProps {
  uplinkId: UplinkId;
  activeCloudAgentId: string | null;
  /** Cloud Agent uplink only: pass from Chat (mission modal + persistence). */
  cloudMissionHandling?: CloudMissionHandling;
  onManagedSnapshotChange?: (snapshot: ManagedMissionSnapshot | null) => void;
  managedPollRefreshNonce?: number;
  embedUrl: string;
  onEmbedUrlChange: (v: string) => void;
  requestedTabId?: WarRoomTabId;
  requestedTabNonce?: number;
  browserOnly?: boolean;
}

/**
 * Uplink-specific execution surface (tabs + panels). Used for War Room and Split right pane.
 */
export function WarRoomPane({
  uplinkId,
  activeCloudAgentId,
  cloudMissionHandling,
  onManagedSnapshotChange,
  managedPollRefreshNonce,
  embedUrl,
  onEmbedUrlChange,
  requestedTabId,
  requestedTabNonce,
  browserOnly,
}: WarRoomPaneProps) {
  return (
    <div className="flex h-full min-h-0 w-full min-w-0 flex-1 flex-col">
      {browserOnly ? (
        <div className="flex flex-1 min-h-0 p-2">
          <BrowserTabPanel embedUrl={embedUrl} onEmbedUrlChange={onEmbedUrlChange} autoStart />
        </div>
      ) : uplinkId === "cloud_agent" ? (
        <CloudAgentPanel
          activeCloudAgentId={activeCloudAgentId}
          cloudMissionHandling={cloudMissionHandling}
          onManagedSnapshotChange={onManagedSnapshotChange}
          managedPollRefreshNonce={managedPollRefreshNonce}
          embedUrl={embedUrl}
          onEmbedUrlChange={onEmbedUrlChange}
          requestedTabId={requestedTabId}
          requestedTabNonce={requestedTabNonce}
        />
      ) : uplinkId === "factory_ai" ? (
        <FactoryAIPanel
          embedUrl={embedUrl}
          onEmbedUrlChange={onEmbedUrlChange}
          requestedTabId={requestedTabId}
          requestedTabNonce={requestedTabNonce}
        />
      ) : (
        <ElizaOsPanel
          embedUrl={embedUrl}
          onEmbedUrlChange={onEmbedUrlChange}
          requestedTabId={requestedTabId}
          requestedTabNonce={requestedTabNonce}
        />
      )}
    </div>
  );
}
