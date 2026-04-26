/**
 * Local UI / adapter shapes for the namespaced Hermes Workspace lift.
 */

export type WorkspaceNamespace = "hermes-workspace-lift";

export type WorkspaceChatMessageRole = "user" | "assistant" | "system";

export type WorkspaceChatMessage = {
  id: string;
  role: WorkspaceChatMessageRole;
  content: string;
  timestamp: string;
};
