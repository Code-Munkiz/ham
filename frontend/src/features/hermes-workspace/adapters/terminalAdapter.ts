/**
 * HAM-owned terminal bridge: `/api/workspace/terminal/*`.
 * Upstream: `/api/terminal-input`, `/api/terminal-resize` (mapped to namespaced sessions).
 */

const TBASE = "/api/workspace/terminal";

export type TerminalBridgeState =
  | { status: "ready" }
  | { status: "pending"; detail: string };

const PENDING: TerminalBridgeState = { status: "pending", detail: "Runtime bridge pending" };

export const workspaceTerminalAdapter = {
  description: "HAM /api/workspace/terminal/sessions — subprocess bridge; output polled via /output.",

  async createSession(_tabId: string): Promise<{ sessionId: string | null; bridge: TerminalBridgeState }> {
    try {
      const res = await fetch(`${TBASE}/sessions`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "include",
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        return { sessionId: null, bridge: PENDING };
      }
      const data = (await res.json()) as { sessionId?: string };
      return {
        sessionId: typeof data.sessionId === "string" ? data.sessionId : null,
        bridge: data.sessionId ? { status: "ready" } : PENDING,
      };
    } catch {
      return { sessionId: null, bridge: PENDING };
    }
  },

  async sendInput(sessionId: string, data: string): Promise<{ ok: boolean; bridge: TerminalBridgeState }> {
    if (!sessionId) {
      return { ok: false, bridge: PENDING };
    }
    try {
      const res = await fetch(`${TBASE}/sessions/${encodeURIComponent(sessionId)}/input`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ data }),
      });
      if (!res.ok) {
        return { ok: false, bridge: PENDING };
      }
      return { ok: true, bridge: { status: "ready" } };
    } catch {
      return { ok: false, bridge: PENDING };
    }
  },

  async resize(
    sessionId: string,
    cols: number,
    rows: number,
  ): Promise<{ ok: boolean; bridge: TerminalBridgeState }> {
    if (!sessionId) {
      return { ok: false, bridge: PENDING };
    }
    try {
      const res = await fetch(`${TBASE}/sessions/${encodeURIComponent(sessionId)}/resize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ cols, rows }),
      });
      if (!res.ok) {
        return { ok: false, bridge: PENDING };
      }
      return { ok: true, bridge: { status: "ready" } };
    } catch {
      return { ok: false, bridge: PENDING };
    }
  },

  async pollOutput(
    sessionId: string,
    after: number,
  ): Promise<{
    text: string;
    next: number;
    bridge: TerminalBridgeState;
  }> {
    if (!sessionId) {
      return { text: "", next: after, bridge: PENDING };
    }
    try {
      const res = await fetch(
        `${TBASE}/sessions/${encodeURIComponent(sessionId)}/output?after=${after}`,
        { credentials: "include" },
      );
      if (!res.ok) {
        return { text: "", next: after, bridge: PENDING };
      }
      const data = (await res.json()) as { text?: string; next?: number; len?: number };
      const text = typeof data.text === "string" ? data.text : "";
      const next = typeof data.next === "number" ? data.next : after + text.length;
      return { text, next, bridge: { status: "ready" } };
    } catch {
      return { text: "", next: after, bridge: PENDING };
    }
  },

  async closeSession(sessionId: string): Promise<void> {
    try {
      await fetch(`${TBASE}/sessions/${encodeURIComponent(sessionId)}`, {
        method: "DELETE",
        credentials: "include",
      });
    } catch {
      /* ignore */
    }
  },
} as const;
