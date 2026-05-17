import type { CodingConductorPreviewPayload } from "@/lib/ham/api";

const STORAGE_PREFIX = "hww.chat.codingPlanDraft.v1:";
/** Drafts expire so stale conductors are not revived after long idle periods. */
const MAX_DRAFT_AGE_MS = 1000 * 60 * 60 * 48; // 48h

function normalizedKeyPart(id: string | null | undefined): string | null {
  const v = id?.trim();
  return v ? v : null;
}

function draftStorageKey(workspaceId: string | null, sessionId: string | null): string | null {
  const ws = normalizedKeyPart(workspaceId);
  const sid = normalizedKeyPart(sessionId);
  if (!ws || !sid) return null;
  return `${STORAGE_PREFIX}${ws}:${sid}`;
}

type DraftEnvelopeV1 = {
  v: 1;
  savedAt: number;
  prompt: string;
  preview: CodingConductorPreviewPayload;
};

export function persistCodingPlanDraft(
  workspaceId: string | null,
  sessionId: string | null,
  prompt: string,
  preview: CodingConductorPreviewPayload,
): void {
  if (typeof window === "undefined") return;
  const key = draftStorageKey(workspaceId, sessionId);
  if (!key) return;
  try {
    const envelope: DraftEnvelopeV1 = {
      v: 1,
      savedAt: Date.now(),
      prompt,
      preview,
    };
    window.sessionStorage.setItem(key, JSON.stringify(envelope));
  } catch {
    /* quota / privacy mode — non-fatal */
  }
}

export function readCodingPlanDraft(
  workspaceId: string | null,
  sessionId: string | null,
): { prompt: string; preview: CodingConductorPreviewPayload } | null {
  if (typeof window === "undefined") return null;
  const key = draftStorageKey(workspaceId, sessionId);
  if (!key) return null;
  try {
    const raw = window.sessionStorage.getItem(key);
    if (!raw?.trim()) return null;
    const parsed = JSON.parse(raw) as DraftEnvelopeV1;
    if (parsed?.v !== 1 || typeof parsed.prompt !== "string" || !parsed.preview) return null;
    if (
      typeof parsed.savedAt !== "number" ||
      !Number.isFinite(parsed.savedAt) ||
      Date.now() - parsed.savedAt > MAX_DRAFT_AGE_MS
    ) {
      window.sessionStorage.removeItem(key);
      return null;
    }
    return { prompt: parsed.prompt, preview: parsed.preview };
  } catch {
    try {
      window.sessionStorage.removeItem(key);
    } catch {
      /* ignore */
    }
    return null;
  }
}

export function clearCodingPlanDraft(workspaceId: string | null, sessionId: string | null): void {
  if (typeof window === "undefined") return;
  const key = draftStorageKey(workspaceId, sessionId);
  if (!key) return;
  try {
    window.sessionStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

export function clearCodingPlanDraftsForWorkspace(workspaceId: string | null): void {
  if (typeof window === "undefined") return;
  const ws = normalizedKeyPart(workspaceId);
  if (!ws) return;
  const prefix = `${STORAGE_PREFIX}${ws}:`;
  try {
    const toRemove: string[] = [];
    for (let i = 0; i < window.sessionStorage.length; i++) {
      const k = window.sessionStorage.key(i);
      if (k?.startsWith(prefix)) toRemove.push(k);
    }
    for (const k of toRemove) {
      window.sessionStorage.removeItem(k);
    }
  } catch {
    /* ignore */
  }
}
