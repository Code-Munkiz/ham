/**
 * HAM transport adapters for the namespaced Hermes Workspace lift.
 * Chat streaming is routed exclusively through `postChatStream` (no upstream Workspace VM routes).
 */
import {
  deleteChatSession,
  fetchChatSession,
  fetchChatSessions,
  postChatStream,
  type HamChatRequest,
  type HamChatResponse,
  type HamChatStreamAuth,
} from "@/lib/ham/api";
import { getRegisteredClerkSessionToken } from "@/lib/ham/clerkSession";

export type WorkspaceStreamCallbacks = {
  onSession?: (sessionId: string) => void;
  onDelta?: (text: string) => void;
};

function clerkPublishableKeyPresent(): boolean {
  return Boolean((import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined)?.trim());
}

/**
 * Resolves stream auth the same way as main `/chat`: Clerk JWT when a publishable key is configured.
 * Uses the registered `getToken` from `ClerkAccessBridge` so this works outside React.
 */
export async function getWorkspaceStreamAuth(): Promise<HamChatStreamAuth | undefined> {
  if (!clerkPublishableKeyPresent()) return undefined;
  return { sessionToken: await getRegisteredClerkSessionToken() };
}

/**
 * Thin wrapper: every workspace chat turn goes through HAM’s NDJSON stream contract.
 */
export async function runWorkspaceChatStream(
  body: HamChatRequest,
  callbacks: WorkspaceStreamCallbacks = {},
  authorization?: HamChatStreamAuth,
): Promise<HamChatResponse> {
  return postChatStream(body, callbacks, authorization);
}

/**
 * Public adapter surface for `/workspace/chat` and future stream-aware workspace panels.
 */
export const workspaceChatAdapter = {
  ready: true as const,
  description: "HAM /api/chat/stream via postChatStream (NDJSON: session, delta, done, error)",

  getStreamAuth: getWorkspaceStreamAuth,
  /**
   * Delegates to `postChatStream` in `@/lib/ham/api` — the single HAM entry point for browser chat streaming.
   */
  stream: runWorkspaceChatStream,
} as const;

/**
 * HAM chat history — `fetchChatSessions` / `fetchChatSession` from `@/lib/ham/api` only (no new transport).
 */
export const workspaceSessionAdapter = {
  ready: true as const,
  list: (limit = 50, offset = 0, workspaceId?: string | null) =>
    fetchChatSessions(limit, offset, workspaceId),
  get: (sessionId: string, workspaceId?: string | null) => fetchChatSession(sessionId, workspaceId),
  delete: (sessionId: string, workspaceId?: string | null) => deleteChatSession(sessionId, workspaceId),
} as const;

export { workspaceFileAdapter } from "./adapters/filesAdapter";
export { workspaceJobsAdapter } from "./adapters/jobsAdapter";
export { workspaceTasksAdapter } from "./adapters/tasksAdapter";
export { workspaceTerminalAdapter } from "./adapters/terminalAdapter";
export { workspaceConductorAdapter } from "./adapters/conductorAdapter";
export { workspaceMemoryAdapter } from "./adapters/memoryAdapter";
export { workspaceOperationsAdapter } from "./adapters/operationsAdapter";
export { workspaceProfilesAdapter } from "./adapters/profilesAdapter";
export { workspaceSkillsAdapter } from "./adapters/skillsAdapter";
