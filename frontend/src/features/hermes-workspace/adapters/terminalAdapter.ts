/**
 * HAM-owned terminal bridge: local `/api/workspace/terminal/*` + WebSocket stream.
 * Uses the same local runtime as Files (`hww.localRuntimeBase`); not `VITE_HAM_API_BASE`.
 */

import { isLocalRuntimeConfigured, localRuntimeFetch, localRuntimeWsUrl } from "./localRuntime";

const TBASE = "/api/workspace/terminal";

export type TerminalBridgeLocalCode = "unconfigured" | "unreachable" | "wrong_api";

export type TerminalBridgeState =
  | { status: "ready" }
  | { status: "pending"; detail: string; localCode?: TerminalBridgeLocalCode };

const DISCONNECT =
  "Set the local HAM API URL in Workspace → Settings → Connection, then start uvicorn on that host.";

function bridgeUnconfigured(): TerminalBridgeState {
  return {
    status: "pending",
    detail: `Local runtime not connected. ${DISCONNECT}`,
    localCode: "unconfigured",
  };
}

function bridgeFromHttp(res: Response): TerminalBridgeState {
  if (res.status === 404) {
    return {
      status: "pending",
      detail: "Wrong API — /api/workspace/terminal not found. Is this the Ham FastAPI origin?",
      localCode: "wrong_api",
    };
  }
  return {
    status: "pending",
    detail: `Local terminal API error (HTTP ${res.status}). ${DISCONNECT}`,
    localCode: "unreachable",
  };
}

function bridgeFromError(e: unknown): TerminalBridgeState {
  const msg = e instanceof Error ? e.message : String(e);
  if (msg === "local_runtime_unconfigured") {
    return bridgeUnconfigured();
  }
  return {
    status: "pending",
    detail: `Not reachable: ${msg}`,
    localCode: "unreachable",
  };
}

export const workspaceTerminalAdapter = {
  description:
    "HAM /api/workspace/terminal on the **local** machine — ConPTY (Windows) or pipe; output via WebSocket /stream and/or HTTP /output.",

  /** WebSocket URL for terminal output on the local runtime, or `""` if unconfigured. */
  webSocketStreamUrl(sessionId: string): string {
    if (typeof window === "undefined" || !sessionId) {
      return "";
    }
    const rel = `${TBASE}/sessions/${encodeURIComponent(sessionId)}/stream`;
    if (!isLocalRuntimeConfigured()) {
      return "";
    }
    return localRuntimeWsUrl(rel);
  },

  async createSession(_tabId: string): Promise<{
    sessionId: string | null;
    transport: "pty" | "pipe" | null;
    streamPath: string | null;
    bridge: TerminalBridgeState;
  }> {
    if (!isLocalRuntimeConfigured()) {
      return { sessionId: null, transport: null, streamPath: null, bridge: bridgeUnconfigured() };
    }
    try {
      const res = await localRuntimeFetch(`${TBASE}/sessions`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ cols: 80, rows: 24 }),
      });
      if (!res.ok) {
        return { sessionId: null, transport: null, streamPath: null, bridge: bridgeFromHttp(res) };
      }
      const data = (await res.json()) as {
        sessionId?: string;
        transport?: string;
        streamPath?: string;
      };
      const sid = typeof data.sessionId === "string" ? data.sessionId : null;
      const transport =
        data.transport === "pty" || data.transport === "pipe" ? data.transport : null;
      return {
        sessionId: sid,
        transport,
        streamPath: typeof data.streamPath === "string" ? data.streamPath : null,
        bridge: data.sessionId ? { status: "ready" } : bridgeUnconfigured(),
      };
    } catch (e) {
      return { sessionId: null, transport: null, streamPath: null, bridge: bridgeFromError(e) };
    }
  },

  async sendInput(
    sessionId: string,
    data: string,
  ): Promise<{ ok: boolean; bridge: TerminalBridgeState }> {
    if (!isLocalRuntimeConfigured()) {
      return { ok: false, bridge: bridgeUnconfigured() };
    }
    if (!sessionId) {
      return { ok: false, bridge: bridgeUnconfigured() };
    }
    try {
      const res = await localRuntimeFetch(
        `${TBASE}/sessions/${encodeURIComponent(sessionId)}/input`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ data }),
        },
      );
      if (!res.ok) {
        return { ok: false, bridge: bridgeFromHttp(res) };
      }
      return { ok: true, bridge: { status: "ready" } };
    } catch (e) {
      return { ok: false, bridge: bridgeFromError(e) };
    }
  },

  async resize(
    sessionId: string,
    cols: number,
    rows: number,
  ): Promise<{ ok: boolean; bridge: TerminalBridgeState }> {
    if (!isLocalRuntimeConfigured() || !sessionId) {
      return { ok: false, bridge: bridgeUnconfigured() };
    }
    try {
      const res = await localRuntimeFetch(
        `${TBASE}/sessions/${encodeURIComponent(sessionId)}/resize`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ cols, rows }),
        },
      );
      if (!res.ok) {
        return { ok: false, bridge: bridgeFromHttp(res) };
      }
      return { ok: true, bridge: { status: "ready" } };
    } catch (e) {
      return { ok: false, bridge: bridgeFromError(e) };
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
    if (!isLocalRuntimeConfigured() || !sessionId) {
      return { text: "", next: after, bridge: bridgeUnconfigured() };
    }
    try {
      const res = await localRuntimeFetch(
        `${TBASE}/sessions/${encodeURIComponent(sessionId)}/output?after=${after}`,
        { method: "GET" },
      );
      if (!res.ok) {
        return { text: "", next: after, bridge: bridgeFromHttp(res) };
      }
      const data = (await res.json()) as { text?: string; next?: number; len?: number };
      const text = typeof data.text === "string" ? data.text : "";
      const next = typeof data.next === "number" ? data.next : after + text.length;
      return { text, next, bridge: { status: "ready" } };
    } catch (e) {
      return { text: "", next: after, bridge: bridgeFromError(e) };
    }
  },

  async closeSession(sessionId: string): Promise<void> {
    if (!isLocalRuntimeConfigured() || !sessionId) {
      return;
    }
    try {
      await localRuntimeFetch(`${TBASE}/sessions/${encodeURIComponent(sessionId)}`, {
        method: "DELETE",
      });
    } catch {
      /* ignore */
    }
  },
} as const;
