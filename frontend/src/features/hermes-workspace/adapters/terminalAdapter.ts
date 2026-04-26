/**
 * `workspaceTerminalAdapter` — single surface for Terminal IA. PTY/session bridge gaps
 * stay here. Upstream reference: `src/components/terminal/terminal-workspace.tsx`
 * (`/api/terminal-input`, `/api/terminal-resize`, session bootstrap in-file).
 */

export type TerminalBridgeState =
  | { status: "ready" }
  | { status: "pending"; detail: string };

const PENDING: TerminalBridgeState = { status: "pending", detail: "Runtime bridge pending" };

export const workspaceTerminalAdapter = {
  description:
    "Browser terminal; Hermes used terminal-input/resize and session id per tab — HAM may wire without changing call sites here.",

  /**
   * Best-effort session creation. If no backend session endpoint responds, returns null id + pending.
   */
  async createSession(_tabId: string): Promise<{ sessionId: string | null; bridge: TerminalBridgeState }> {
    try {
      const res = await fetch("/api/terminal-session", {
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
      const res = await fetch("/api/terminal-input", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ sessionId, data }),
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
      const res = await fetch("/api/terminal-resize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ sessionId, cols, rows }),
      });
      if (!res.ok) {
        return { ok: false, bridge: PENDING };
      }
      return { ok: true, bridge: { status: "ready" } };
    } catch {
      return { ok: false, bridge: PENDING };
    }
  },
} as const;
