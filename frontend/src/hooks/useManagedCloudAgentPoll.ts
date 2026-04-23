import * as React from "react";

import { fetchCursorAgent, fetchCursorAgentConversation } from "@/lib/ham/api";
import {
  deriveManagedMissionReview,
  deriveManagedMissionSnapshot,
  MANAGED_CLOUD_AGENT_POLL_MS,
  shouldEmitReviewChatLine,
} from "@/lib/ham/managedCloudAgent";
import type { ManagedMissionReview, ManagedMissionSnapshot } from "@/lib/ham/types";

export type UseManagedCloudAgentPollOptions = {
  enabled: boolean;
  /** Trimmed agent id; when `enabled` is false may be empty */
  agentId: string;
  onAfterSuccess: (agent: Record<string, unknown>, conversation: unknown) => void;
  /** Optional: terminal-only, when review adds value; dedupe in the consumer (e.g. Chat). */
  onTerminalReviewForChat?: (
    agent: Record<string, unknown>,
    conversation: unknown,
    review: ManagedMissionReview,
  ) => void;
};

/**
 * Single owner for managed Cloud Agent agent+conversation polling (one interval when enabled).
 */
export function useManagedCloudAgentPoll(options: UseManagedCloudAgentPollOptions): {
  lastSnapshot: ManagedMissionSnapshot | null;
  lastReview: ManagedMissionReview | null;
  lastUpdated: number | null;
  pollError: string | null;
  pollPending: boolean;
  refresh: () => void;
} {
  const { enabled, agentId, onAfterSuccess, onTerminalReviewForChat } = options;
  const [lastSnapshot, setLastSnapshot] = React.useState<ManagedMissionSnapshot | null>(null);
  const [lastReview, setLastReview] = React.useState<ManagedMissionReview | null>(null);
  const [lastUpdated, setLastUpdated] = React.useState<number | null>(null);
  const [pollError, setPollError] = React.useState<string | null>(null);
  const [pollPending, setPollPending] = React.useState(false);

  const enabledRef = React.useRef(enabled);
  const agentIdRef = React.useRef(agentId);
  const onAfterSuccessRef = React.useRef(onAfterSuccess);
  const onTerminalReviewForChatRef = React.useRef(onTerminalReviewForChat);
  const inFlightCountRef = React.useRef(0);
  enabledRef.current = enabled;
  agentIdRef.current = agentId;
  onAfterSuccessRef.current = onAfterSuccess;
  onTerminalReviewForChatRef.current = onTerminalReviewForChat;

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
      const review = deriveManagedMissionReview(agent, conv, snap);
      setLastSnapshot(snap);
      setLastReview(review);
      setLastUpdated(Date.now());
      onAfterSuccessRef.current(agent, conv);
      const rvc = onTerminalReviewForChatRef.current;
      if (rvc && shouldEmitReviewChatLine(review)) {
        rvc(agent, conv, review);
      }
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
      setLastReview(null);
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
    lastReview,
    lastUpdated,
    pollError,
    pollPending,
    refresh,
  };
}
