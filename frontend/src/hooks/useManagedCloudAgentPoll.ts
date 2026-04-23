import * as React from "react";

import { fetchCursorAgent, fetchCursorAgentConversation } from "@/lib/ham/api";
import {
  deriveManagedMissionSnapshot,
  MANAGED_CLOUD_AGENT_POLL_MS,
} from "@/lib/ham/managedCloudAgent";
import type { ManagedMissionSnapshot } from "@/lib/ham/types";

export type UseManagedCloudAgentPollOptions = {
  enabled: boolean;
  /** Trimmed agent id; when `enabled` is false may be empty */
  agentId: string;
  onAfterSuccess: (agent: Record<string, unknown>, conversation: unknown) => void;
};

/**
 * Single owner for managed Cloud Agent agent+conversation polling (one interval when enabled).
 */
export function useManagedCloudAgentPoll(options: UseManagedCloudAgentPollOptions): {
  lastSnapshot: ManagedMissionSnapshot | null;
  lastUpdated: number | null;
  pollError: string | null;
  pollPending: boolean;
  refresh: () => void;
} {
  const { enabled, agentId, onAfterSuccess } = options;
  const [lastSnapshot, setLastSnapshot] = React.useState<ManagedMissionSnapshot | null>(null);
  const [lastUpdated, setLastUpdated] = React.useState<number | null>(null);
  const [pollError, setPollError] = React.useState<string | null>(null);
  const [pollPending, setPollPending] = React.useState(false);

  const enabledRef = React.useRef(enabled);
  const agentIdRef = React.useRef(agentId);
  const onAfterSuccessRef = React.useRef(onAfterSuccess);
  const inFlightCountRef = React.useRef(0);
  enabledRef.current = enabled;
  agentIdRef.current = agentId;
  onAfterSuccessRef.current = onAfterSuccess;

  const runPoll = React.useCallback(async () => {
    if (!enabledRef.current) return;
    const id = agentIdRef.current.trim();
    if (!id) return;
    const requestId = id;
    inFlightCountRef.current += 1;
    if (inFlightCountRef.current === 1) {
      setPollPending(true);
    }
    setPollError(null);
    try {
      const [agent, conv] = await Promise.all([
        fetchCursorAgent(requestId),
        fetchCursorAgentConversation(requestId),
      ]);
      if (!enabledRef.current || agentIdRef.current.trim() !== requestId) {
        return;
      }
      const snap = deriveManagedMissionSnapshot(agent, conv);
      setLastSnapshot(snap);
      setLastUpdated(Date.now());
      onAfterSuccessRef.current(agent, conv);
    } catch (e: unknown) {
      if (!enabledRef.current || agentIdRef.current.trim() !== requestId) {
        return;
      }
      setPollError(e instanceof Error ? e.message : "Request failed");
    } finally {
      inFlightCountRef.current -= 1;
      if (inFlightCountRef.current === 0) {
        setPollPending(false);
      }
    }
  }, []);

  React.useEffect(() => {
    if (!enabled) {
      inFlightCountRef.current = 0;
      setLastSnapshot(null);
      setLastUpdated(null);
      setPollError(null);
      setPollPending(false);
    }
  }, [enabled]);

  React.useEffect(() => {
    if (!enabled || !agentId.trim()) {
      return;
    }
    let dead = false;
    void (async () => {
      if (dead) return;
      await runPoll();
    })();
    const t = window.setInterval(() => {
      if (!dead) void runPoll();
    }, MANAGED_CLOUD_AGENT_POLL_MS);
    return () => {
      dead = true;
      window.clearInterval(t);
    };
  }, [enabled, agentId, runPoll]);

  const refresh = React.useCallback(() => {
    void runPoll();
  }, [runPoll]);

  return {
    lastSnapshot,
    lastUpdated,
    pollError,
    pollPending,
    refresh,
  };
}
