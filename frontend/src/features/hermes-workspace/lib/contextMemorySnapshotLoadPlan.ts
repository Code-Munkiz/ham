/**
 * Pure load plan for Context & Memory snapshot (local vs cloud). Used by
 * {@link ContextAndMemoryPanel} and unit-tested without React.
 */

import type { ContextEnginePayload } from "@/lib/ham/types";

export type ContextMemorySnapshotSource = "local" | "project" | "global";

export type LocalRuntimeHealthLike = {
  ok?: boolean;
  workspaceRootConfigured?: boolean;
} | null;

export type ContextMemorySnapshotLoadDeps = {
  isLocalRuntimeConfigured: () => boolean;
  fetchLocalWorkspaceHealth: () => Promise<LocalRuntimeHealthLike>;
  fetchLocalWorkspaceContextSnapshot: () => Promise<ContextEnginePayload>;
  fetchProjectContextEngine: (projectId: string) => Promise<ContextEnginePayload>;
  fetchContextEngine: () => Promise<ContextEnginePayload>;
};

export type ContextMemorySnapshotLoadOutcome = {
  payload: ContextEnginePayload;
  source: ContextMemorySnapshotSource;
  fallbackNote: string | null;
};

/** True when cloud settings Preview/Apply must not run against this view. */
export function shouldGateContextMemorySettingsMutations(
  source: ContextMemorySnapshotSource | null,
): boolean {
  return source === "local";
}

/** True when payload is from the local workspace snapshot route. */
export function isLocalContextEnginePayload(payload: ContextEnginePayload | null): boolean {
  return payload?.context_source === "local";
}

/**
 * Prefer local snapshot when runtime is configured, health is OK, and workspace root is set in env.
 * Otherwise use project-scoped cloud, then global cloud (same order as the panel).
 */
export async function loadContextMemorySnapshot(
  hamProjectId: string | null,
  deps: ContextMemorySnapshotLoadDeps,
): Promise<ContextMemorySnapshotLoadOutcome> {
  let fallbackNote: string | null = null;

  if (deps.isLocalRuntimeConfigured()) {
    const health = await deps.fetchLocalWorkspaceHealth();
    if (health?.ok === true && health.workspaceRootConfigured === true) {
      try {
        const localPayload = await deps.fetchLocalWorkspaceContextSnapshot();
        return {
          payload: { ...localPayload, context_source: "local" },
          source: "local",
          fallbackNote: null,
        };
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Local snapshot failed";
        fallbackNote = `This computer did not return a project snapshot (${msg}). Showing the cloud snapshot instead.`;
      }
    }
  }

  if (hamProjectId) {
    try {
      const payload = await deps.fetchProjectContextEngine(hamProjectId);
      return {
        payload: { ...payload, context_source: "cloud" },
        source: "project",
        fallbackNote,
      };
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Project snapshot failed";
      fallbackNote = `Could not load the cloud project snapshot (${msg}). Showing the global cloud API snapshot instead — this is normal when the cloud host does not have that project folder.`;
      const payload = await deps.fetchContextEngine();
      return {
        payload: { ...payload, context_source: "cloud" },
        source: "global",
        fallbackNote,
      };
    }
  }

  const payload = await deps.fetchContextEngine();
  return {
    payload: { ...payload, context_source: "cloud" },
    source: "global",
    fallbackNote,
  };
}
