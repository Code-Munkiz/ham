import * as React from "react";

import {
  fetchCursorAgent,
  fetchCursorAgentConversation,
  fetchManagedMissionForAgent,
} from "@/lib/ham/api";
import {
  deriveManagedDeployReadiness,
  deriveManagedMissionReview,
  deriveManagedMissionSnapshot,
  MANAGED_CLOUD_AGENT_POLL_MS,
  shouldEmitReviewChatLine,
} from "@/lib/ham/managedCloudAgent";
import type {
  ManagedDeployReadiness,
  ManagedMissionReview,
  ManagedMissionSnapshot,
} from "@/lib/ham/types";

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
  lastDeployReadiness: ManagedDeployReadiness | null;
  lastUpdated: number | null;
  pollError: string | null;
  pollPending: boolean;
  refresh: () => void;
} {
  const { enabled, agentId, onAfterSuccess, onTerminalReviewForChat } = options;
  const [lastSnapshot, setLastSnapshot] = React.useState<ManagedMissionSnapshot | null>(null);
  const [lastReview, setLastReview] = React.useState<ManagedMissionReview | null>(null);
  const [lastDeployReadiness, setLastDeployReadiness] = React.useState<ManagedDeployReadiness | null>(null);
  const [lastUpdated, setLastUpdated] = React.useState<number | null>(null);
  const [pollError, setPollError] = React.useState<string | null>(null);
  const [pollPending, setPollPending] = React.useState(false);

  const enabledRef = React.useRef(enabled);
  const agentIdRef = React.useRef(agentId);
  const onAfterSuccessRef = React.useRef(onAfterSuccess);
  const onTerminalReviewForChatRef = React.useRef(onTerminalReviewForChat);
  const inFlightCountRef = React.useRef(0);
  /** Latest `mission_lifecycle` from ManagedMission store (null = unknown / no row). */
  const missionLifecycleRef = React.useRef<string | null>(null);
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
      let missionLc: string | null = null;
      try {
        const mission = await fetchManagedMissionForAgent(requestId);
        missionLc = mission?.mission_lifecycle?.trim().toLowerCase() ?? null;
      } catch {
        missionLc = null;
      }
      missionLifecycleRef.current = missionLc;

      const snap = deriveManagedMissionSnapshot(agent, conv);
      const review = deriveManagedMissionReview(agent, conv, snap);
      const deploy = deriveManagedDeployReadiness(agent, conv, snap, review);
      setLastSnapshot(snap);
      setLastReview(review);
      setLastDeployReadiness(deploy);
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
      missionLifecycleRef.current = null;
      setLastSnapshot(null);
      setLastReview(null);
      setLastDeployReadiness(null);
      setLastUpdated(null);
      setPollError(null);
      setPollPending(false);
    }
  }, [enabled]);

  /** Single polling loop: run immediately, then every MANAGED_CLOUD_AGENT_POLL_MS while lifecycle is non-terminal. */
  React.useEffect(() => {
    if (!enabled || !agentId.trim()) {
      return;
    }
    let dead = false;
    let tid: number | undefined;

    const tick = async () => {
      if (dead || !enabledRef.current) return;
      await runPoll();
      if (dead || !enabledRef.current) return;
      const lc = missionLifecycleRef.current;
      const terminal = lc === "succeeded" || lc === "failed" || lc === "archived";
      if (!terminal) {
        tid = window.setTimeout(() => void tick(), MANAGED_CLOUD_AGENT_POLL_MS);
      }
    };

    void tick();

    return () => {
      dead = true;
      if (tid !== undefined) window.clearTimeout(tid);
    };
  }, [enabled, agentId, runPoll]);

  const refresh = React.useCallback(() => {
    void runPoll();
  }, [runPoll]);

  return {
    lastSnapshot,
    lastReview,
    lastDeployReadiness,
    lastUpdated,
    pollError,
    pollPending,
    refresh,
  };
}
