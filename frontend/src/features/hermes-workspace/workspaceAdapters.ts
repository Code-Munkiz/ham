/**
 * Placeholder adapters for the namespaced Hermes Workspace lift.
 * Real wiring: postChatStream, sessions, etc. — see docs/WHOLE_HERMES_WORKSPACE_LIFT_PLAN.md
 */
export const workspaceChatAdapter = {
  ready: false as const,
  description: "Wire to postChatStream in a follow-up commit",
} as const;

export const workspaceSessionAdapter = {
  ready: false as const,
} as const;

export const workspaceVoiceAdapter = {
  ready: false as const,
} as const;

export const workspaceAttachmentAdapter = {
  ready: false as const,
} as const;
