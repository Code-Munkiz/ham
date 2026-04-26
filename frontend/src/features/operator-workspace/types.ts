import type { UplinkId, WorkbenchMode } from "@/components/chat/ChatComposerStrip";

export type OperatorMessageRole = "user" | "assistant" | "system";

export interface OperatorMessage {
  id: string;
  role: OperatorMessageRole;
  content: string;
  timestamp: string;
}

export interface OperatorWorkspaceCapabilities {
  uplinkId: UplinkId;
  workbenchMode: WorkbenchMode;
  activeCloudAgentId: string | null;
  cloudMissionHandling: string;
}

export interface OperatorSessionItem {
  sessionId: string;
  preview: string;
  turnCount: number;
  createdAt: string | null;
  isActive: boolean;
}

export type OperatorAttachmentKind = "image" | "text" | "binary";

export interface OperatorAttachment {
  id: string;
  name: string;
  size: number;
  kind: OperatorAttachmentKind;
  payload: string;
}

