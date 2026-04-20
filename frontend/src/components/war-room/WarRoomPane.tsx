import type { UplinkId } from "@/components/chat/ChatComposerStrip";

import { CloudAgentPanel } from "./CloudAgentPanel";
import { ElizaOsPanel } from "./ElizaOsPanel";
import { FactoryAIPanel } from "./FactoryAIPanel";

export interface WarRoomPaneProps {
  uplinkId: UplinkId;
  activeCloudAgentId: string | null;
  embedUrl: string;
  onEmbedUrlChange: (v: string) => void;
}

/**
 * Uplink-specific execution surface (tabs + panels). Used for War Room and Split right pane.
 */
export function WarRoomPane({ uplinkId, activeCloudAgentId, embedUrl, onEmbedUrlChange }: WarRoomPaneProps) {
  return (
    <div className="flex h-full min-h-0 w-full min-w-0 flex-1 flex-col">
      {uplinkId === "cloud_agent" ? (
        <CloudAgentPanel
          activeCloudAgentId={activeCloudAgentId}
          embedUrl={embedUrl}
          onEmbedUrlChange={onEmbedUrlChange}
        />
      ) : uplinkId === "factory_ai" ? (
        <FactoryAIPanel embedUrl={embedUrl} onEmbedUrlChange={onEmbedUrlChange} />
      ) : (
        <ElizaOsPanel embedUrl={embedUrl} onEmbedUrlChange={onEmbedUrlChange} />
      )}
    </div>
  );
}
