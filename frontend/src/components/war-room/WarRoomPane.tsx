import * as React from "react";

import type { UplinkId } from "@/components/chat/ChatComposerStrip";
import type { CloudMissionHandling } from "@/lib/ham/types";

import { CloudAgentPanel } from "./CloudAgentPanel";
import { ElizaOsPanel } from "./ElizaOsPanel";
import { FactoryAIPanel } from "./FactoryAIPanel";
import { ExecutionSurfaceChrome, type ExecutionChromeMode } from "./ExecutionSurfaceChrome";
import { WarRoomTabs } from "./WarRoomTabs";
import { getDefaultWarRoomTab, getWarRoomTabs, type WarRoomTabId } from "./uplinkConfig";

function visibleTabs(uplink: UplinkId, browserOnly: boolean) {
  const all = getWarRoomTabs(uplink);
  if (browserOnly) return all.filter((t) => t.id === "browser");
  return all;
}

function pickDefaultTab(uplink: UplinkId, browserOnly: boolean): WarRoomTabId {
  const v = visibleTabs(uplink, browserOnly);
  if (v.length === 0) return "browser";
  const d = getDefaultWarRoomTab(uplink);
  if (v.some((t) => t.id === d)) return d;
  return v[0].id;
}

export interface WarRoomPaneProps {
  uplinkId: UplinkId;
  activeCloudAgentId: string | null;
  /** Cloud Agent uplink only: pass from Chat (mission modal + persistence). */
  cloudMissionHandling?: CloudMissionHandling;
  embedUrl: string;
  onEmbedUrlChange: (v: string) => void;
  requestedTabId?: WarRoomTabId;
  requestedTabNonce?: number;
  browserOnly?: boolean;
  executionMode: ExecutionChromeMode;
  onCloseExecution: () => void;
  warRoomSignal?: boolean;
  reduceMotion?: boolean;
  warBlink?: boolean;
  /**
   * When the workbench shows the live mission ribbon, hide the in-pane compact status strip
   * to avoid duplicating the same message under the tab row.
   */
  workbenchMissionBannerActive?: boolean;
  /** Shown in empty / not-connected Cloud Agent state. */
  onOpenProjectsRegistry?: () => void;
}

/**
 * Uplink execution surface: **ExecutionSurfaceChrome** (Option B) + tab strip in the top bar + content below.
 */
export function WarRoomPane({
  uplinkId,
  activeCloudAgentId,
  cloudMissionHandling,
  embedUrl,
  onEmbedUrlChange,
  requestedTabId,
  requestedTabNonce,
  browserOnly = false,
  executionMode,
  onCloseExecution,
  warRoomSignal,
  reduceMotion,
  warBlink,
  workbenchMissionBannerActive = false,
  onOpenProjectsRegistry,
}: WarRoomPaneProps) {
  const vTabs = React.useMemo(() => visibleTabs(uplinkId, browserOnly), [uplinkId, browserOnly]);
  const [tabId, setTabId] = React.useState<WarRoomTabId>(() => pickDefaultTab(uplinkId, browserOnly));

  React.useEffect(() => {
    setTabId(pickDefaultTab(uplinkId, browserOnly));
  }, [uplinkId, browserOnly]);

  React.useEffect(() => {
    if (!requestedTabId || !vTabs.some((t) => t.id === requestedTabId)) return;
    setTabId(requestedTabId);
  }, [requestedTabId, requestedTabNonce, vTabs]);

  React.useEffect(() => {
    if (vTabs.length > 0 && !vTabs.some((t) => t.id === tabId)) {
      setTabId(pickDefaultTab(uplinkId, browserOnly));
    }
  }, [vTabs, tabId, uplinkId, browserOnly]);

  const tabBar = <WarRoomTabs tabs={vTabs} activeId={tabId} onSelect={setTabId} variant="chrome" />;

  return (
    <ExecutionSurfaceChrome
      mode={executionMode}
      onClose={onCloseExecution}
      tabBar={tabBar}
      warRoomSignal={warRoomSignal}
      reduceMotion={reduceMotion}
      warBlink={warBlink}
      browserOnly={browserOnly}
    >
      <div className="flex h-full min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden">
        {uplinkId === "cloud_agent" ? (
          <CloudAgentPanel
            tabId={tabId}
            activeCloudAgentId={activeCloudAgentId}
            cloudMissionHandling={cloudMissionHandling}
            embedUrl={embedUrl}
            onEmbedUrlChange={onEmbedUrlChange}
            workbenchMissionBannerActive={workbenchMissionBannerActive}
            onOpenProjectsRegistry={onOpenProjectsRegistry}
          />
        ) : uplinkId === "factory_ai" ? (
          <FactoryAIPanel tabId={tabId} embedUrl={embedUrl} onEmbedUrlChange={onEmbedUrlChange} />
        ) : (
          <ElizaOsPanel tabId={tabId} embedUrl={embedUrl} onEmbedUrlChange={onEmbedUrlChange} />
        )}
      </div>
    </ExecutionSurfaceChrome>
  );
}
