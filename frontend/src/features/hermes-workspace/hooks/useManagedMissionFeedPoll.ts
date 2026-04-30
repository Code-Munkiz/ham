import * as React from "react";
import {
  fetchManagedMissionFeed,
  managedMissionFeedPollDelayMs,
  type ManagedMissionFeedPayload,
} from "../adapters/managedMissionsAdapter";

export type UseManagedMissionFeedPollOptions = {
  /** Bump (e.g. parent Sync) to force an immediate refetch and reschedule. */
  refreshSignal?: number;
};

/**
 * Bounded automatic REST refresh for a single mission feed (HAM `/feed` only).
 * Not provider streaming: interval slows for terminal missions and hidden tabs.
 */
export function useManagedMissionFeedPoll(
  missionRegistryId: string | null | undefined,
  options?: UseManagedMissionFeedPollOptions,
): {
  feed: ManagedMissionFeedPayload | null;
  error: string | null;
  loading: boolean;
  refetch: () => Promise<ManagedMissionFeedPayload | null>;
} {
  const refreshSignal = options?.refreshSignal ?? 0;
  const trimmed = React.useMemo(() => String(missionRegistryId || "").trim() || null, [missionRegistryId]);

  const [feed, setFeed] = React.useState<ManagedMissionFeedPayload | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);

  const latestFeedRef = React.useRef<ManagedMissionFeedPayload | null>(null);
  const inFlightRef = React.useRef(false);
  const rescheduleRef = React.useRef<(() => void) | null>(null);

  React.useEffect(() => {
    if (!trimmed) {
      rescheduleRef.current = null;
      latestFeedRef.current = null;
      setFeed(null);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    let tid: number | undefined;

    const clearTimer = () => {
      if (tid !== undefined) {
        window.clearTimeout(tid);
        tid = undefined;
      }
    };

    const delayForNext = (): number =>
      managedMissionFeedPollDelayMs(latestFeedRef.current?.lifecycle, document.visibilityState === "hidden");

    const schedule = () => {
      clearTimer();
      if (cancelled) return;
      tid = window.setTimeout(() => void runPoll(), delayForNext());
    };

    const runPoll = async () => {
      if (cancelled || !trimmed || inFlightRef.current) return;
      inFlightRef.current = true;
      setLoading(true);
      try {
        const r = await fetchManagedMissionFeed(trimmed);
        if (cancelled) return;
        const next = r.feed ?? null;
        latestFeedRef.current = next;
        setFeed(next);
        setError(r.error);
      } finally {
        inFlightRef.current = false;
        setLoading(false);
        if (!cancelled) schedule();
      }
    };

    rescheduleRef.current = schedule;

    const kick = async () => {
      if (cancelled || !trimmed || inFlightRef.current) return;
      inFlightRef.current = true;
      setLoading(true);
      try {
        const r = await fetchManagedMissionFeed(trimmed);
        if (cancelled) return;
        const next = r.feed ?? null;
        latestFeedRef.current = next;
        setFeed(next);
        setError(r.error);
      } finally {
        inFlightRef.current = false;
        setLoading(false);
        if (!cancelled) schedule();
      }
    };

    void kick();

    const onVis = () => {
      schedule();
    };
    document.addEventListener("visibilitychange", onVis);

    return () => {
      cancelled = true;
      rescheduleRef.current = null;
      clearTimer();
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [trimmed, refreshSignal]);

  const refetch = React.useCallback(async (): Promise<ManagedMissionFeedPayload | null> => {
    if (!trimmed) return null;
    setLoading(true);
    try {
      const r = await fetchManagedMissionFeed(trimmed);
      const next = r.feed ?? null;
      latestFeedRef.current = next;
      setFeed(next);
      setError(r.error);
      return next;
    } finally {
      setLoading(false);
      rescheduleRef.current?.();
    }
  }, [trimmed]);

  return { feed, error, loading, refetch };
}
