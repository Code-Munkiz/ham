import * as React from "react";
import { apiUrl, mergeClerkAuthBearerIfNeeded } from "@/lib/ham/api";
import {
  fetchManagedMissionFeed,
  managedMissionFeedPollDelayMs,
  isManagedMissionLifecycleTerminal,
  type ManagedMissionFeedEvent,
  type ManagedMissionFeedPayload,
} from "../adapters/managedMissionsAdapter";

type SseMessage = { event: string; data: string };

/** Split SSE buffer into completed ``\\n\\n`` frames; ``carry`` holds a partial trailing frame. */
function feedSse(carry: string, chunk: string): { carry: string; messages: SseMessage[] } {
  const buf = carry + chunk;
  const parts = buf.split("\n\n");
  const nextCarry = parts.pop() ?? "";
  const messages: SseMessage[] = [];
  for (const block of parts) {
    const lines = block.split("\n").filter((l) => l.length > 0);
    let ev = "message";
    const dataLines: string[] = [];
    for (const ln of lines) {
      if (ln.startsWith("event:")) ev = ln.slice(6).trim();
      else if (ln.startsWith("data:")) dataLines.push(ln.slice(5).trimStart());
    }
    if (dataLines.length) messages.push({ event: ev, data: dataLines.join("\n") });
  }
  return { carry: nextCarry, messages };
}

function sortEvents(events: ManagedMissionFeedEvent[]): ManagedMissionFeedEvent[] {
  return [...events].sort((a, b) => `${a.time}\t${a.id}`.localeCompare(`${b.time}\t${b.id}`));
}

function mergeEventsDedup(existing: ManagedMissionFeedEvent[], add: ManagedMissionFeedEvent[]): ManagedMissionFeedEvent[] {
  const m = new Map<string, ManagedMissionFeedEvent>();
  for (const e of existing) m.set(e.id, e);
  for (const e of add) m.set(e.id, e);
  return sortEvents(Array.from(m.values())).slice(-120);
}

function applyMissionEventRow(prev: ManagedMissionFeedPayload | null, row: ManagedMissionFeedEvent): ManagedMissionFeedPayload | null {
  if (!prev) return null;
  return { ...prev, events: mergeEventsDedup(prev.events, [row]) };
}

export type ManagedMissionFeedStreamBanner = {
  phase: "idle" | "connecting" | "live" | "reconnecting" | "poll_only" | "ended";
  label: string;
};

export type UseManagedMissionFeedLiveStreamOptions = {
  refreshSignal?: number;
};

function terminalFromFeed(f: ManagedMissionFeedPayload | null): boolean {
  return Boolean(f?.lifecycle && isManagedMissionLifecycleTerminal(f.lifecycle));
}

/**
 * HAM SSE toward ``GET /feed/stream`` (fetch + ReadableStream, Clerk Bearer like ``hamApiFetch``).
 * Bounded REST polling fills gaps when SSE reconnects fail.
 */
export function useManagedMissionFeedLiveStream(
  missionRegistryId: string | null | undefined,
  options?: UseManagedMissionFeedLiveStreamOptions,
): {
  feed: ManagedMissionFeedPayload | null;
  error: string | null;
  initialLoading: boolean;
  banner: ManagedMissionFeedStreamBanner;
  refetch: () => Promise<ManagedMissionFeedPayload | null>;
  feedScrollAnchorRef: React.RefObject<HTMLDivElement | null>;
} {
  const refreshSignal = options?.refreshSignal ?? 0;
  const trimmed = React.useMemo(() => String(missionRegistryId || "").trim() || null, [missionRegistryId]);

  const [feed, setFeed] = React.useState<ManagedMissionFeedPayload | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [banner, setBanner] = React.useState<ManagedMissionFeedStreamBanner>({ phase: "idle", label: "" });
  const [firstPollDone, setFirstPollDone] = React.useState(false);

  const latestFeedRef = React.useRef<ManagedMissionFeedPayload | null>(null);
  const inFlightPollRef = React.useRef(false);
  const pollScheduleRef = React.useRef<(() => void) | null>(null);
  const sseAbortRef = React.useRef<AbortController | null>(null);

  const seenEventIdsRef = React.useRef<Set<string>>(new Set());
  const lastEventIdRef = React.useRef<string | null>(null);
  const feedScrollAnchorRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    if (!trimmed) {
      sseAbortRef.current?.abort();
      sseAbortRef.current = null;
      pollScheduleRef.current = null;
      latestFeedRef.current = null;
      seenEventIdsRef.current = new Set();
      lastEventIdRef.current = null;
      setFeed(null);
      setError(null);
      setBanner({ phase: "idle", label: "" });
      setFirstPollDone(false);
      return;
    }
    seenEventIdsRef.current = new Set();
    lastEventIdRef.current = null;
    setFirstPollDone(false);

    let cancelled = false;
    let pollTid: number | undefined;

    const clearPoll = () => {
      if (pollTid !== undefined) {
        window.clearTimeout(pollTid);
        pollTid = undefined;
      }
    };

    const delayForPoll = (): number =>
      managedMissionFeedPollDelayMs(latestFeedRef.current?.lifecycle, document.visibilityState === "hidden");

    const schedulePoll = () => {
      clearPoll();
      if (cancelled || !trimmed) return;
      pollTid = window.setTimeout(() => void pollOnce(), delayForPoll());
    };

    const ingestPollPayload = (payload: ManagedMissionFeedPayload | null, err: string | null) => {
      if (cancelled) return;
      if (err && !payload) {
        setError(err);
      } else {
        setError(err);
      }
      if (!payload) {
        setFirstPollDone(true);
        return;
      }
      setFeed(payload);
      latestFeedRef.current = payload;
      for (const e of payload.events) seenEventIdsRef.current.add(e.id);
      const lastId = sortEvents(payload.events).at(-1)?.id;
      if (lastId) lastEventIdRef.current = lastId;
      setFirstPollDone(true);
      const nativeOk =
        payload.provider_projection?.native_realtime_stream === true && payload.provider_projection?.status === "ok";
      setBanner((b) =>
        b.phase === "ended"
          ? b
          : b.phase === "reconnecting"
            ? { phase: "reconnecting", label: "Reconnecting live feed…" }
            : {
                phase: nativeOk ? "live" : "poll_only",
                label: nativeOk ? "Live SDK stream active · HAM SSE" : "SDK stream unavailable — using REST refresh",
              },
      );
      if (terminalFromFeed(payload)) setBanner({ phase: "ended", label: "Mission completed" });
    };

    const pollOnce = async (): Promise<void> => {
      if (cancelled || !trimmed || inFlightPollRef.current) return;
      inFlightPollRef.current = true;
      try {
        const r = await fetchManagedMissionFeed(trimmed);
        if (cancelled) return;
        ingestPollPayload(r.feed ?? null, r.error);
      } finally {
        inFlightPollRef.current = false;
        schedulePoll();
      }
    };

    pollScheduleRef.current = schedulePoll;

    const kick = async () => {
      if (cancelled || !trimmed || inFlightPollRef.current) return;
      inFlightPollRef.current = true;
      try {
        const r = await fetchManagedMissionFeed(trimmed);
        if (cancelled) return;
        ingestPollPayload(r.feed ?? null, r.error);
      } finally {
        inFlightPollRef.current = false;
        schedulePoll();
      }
    };
    void kick();

    document.addEventListener("visibilitychange", schedulePoll);

    return () => {
      cancelled = true;
      clearPoll();
      pollScheduleRef.current = null;
      document.removeEventListener("visibilitychange", schedulePoll);
    };
  }, [trimmed, refreshSignal]);

  React.useEffect(() => {
    if (!trimmed) return;

    let cancelled = false;

    const isTerminalLive = (): boolean => terminalFromFeed(latestFeedRef.current);

    const ingestSnapshot = (snap: ManagedMissionFeedPayload) => {
      if (!snap?.mission_id) return;
      setFeed((prev) => ({ ...snap, events: mergeEventsDedup(prev?.events ?? [], snap.events ?? []) }));
      const mergedLatest = mergeEventsDedup(latestFeedRef.current?.events ?? [], snap.events ?? []);
      latestFeedRef.current = { ...snap, events: mergedLatest };
      for (const ev of mergedLatest) seenEventIdsRef.current.add(ev.id);
      const lid = mergedLatest.at(-1)?.id;
      if (lid) lastEventIdRef.current = lid;
      const nativeOk =
        snap.provider_projection?.native_realtime_stream === true && snap.provider_projection?.status === "ok";
      setBanner({
        phase: terminalFromFeed(snap) ? "ended" : nativeOk ? "live" : "poll_only",
        label: terminalFromFeed(snap)
          ? "Mission completed"
          : nativeOk
            ? "Live SDK stream active · HAM SSE"
            : "SDK stream unavailable — using REST refresh",
      });
    };

    const ingestRow = (row: ManagedMissionFeedEvent) => {
      if (!row?.id || seenEventIdsRef.current.has(row.id)) return;
      seenEventIdsRef.current.add(row.id);
      lastEventIdRef.current = row.id;
      setFeed((prev) => applyMissionEventRow(prev, row));
      latestFeedRef.current = applyMissionEventRow(latestFeedRef.current, row);

      const anchor = feedScrollAnchorRef.current;
      const host = anchor?.parentElement;
      const nearBottom = host ? host.scrollHeight - host.scrollTop - host.clientHeight < 80 : true;
      if (nearBottom && anchor) queueMicrotask(() => anchor.scrollIntoView({ block: "end", behavior: "smooth" }));

      if ((row.kind ?? "") === "completed") setBanner({ phase: "ended", label: "Mission completed" });
    };

    const applyMsg = (msg: SseMessage) => {
      if (!msg.data) return;
      if (msg.event === "snapshot") {
        try {
          ingestSnapshot(JSON.parse(msg.data) as ManagedMissionFeedPayload);
        } catch {
          /* ignore malformed */
        }
        return;
      }
      if (msg.event === "mission_event") {
        try {
          ingestRow(JSON.parse(msg.data) as ManagedMissionFeedEvent);
        } catch {
          /* ignore */
        }
        return;
      }
      if (msg.event === "heartbeat") return;
      if (msg.event === "fallback") {
        setBanner((b) =>
          b.phase === "ended"
            ? b
            : b.phase === "reconnecting"
              ? { phase: "reconnecting", label: "Reconnecting live feed… (REST projection)" }
              : { phase: "poll_only", label: "SDK stream unavailable — using REST refresh" },
        );
        return;
      }
      if (msg.event === "provider_projection") {
        try {
          const proj = JSON.parse(msg.data);
          setFeed((prev) => (prev ? { ...prev, provider_projection: proj } : prev));
          if (latestFeedRef.current) latestFeedRef.current = { ...latestFeedRef.current, provider_projection: proj };
          if (proj?.native_realtime_stream === true && proj?.status === "ok")
            setBanner({ phase: "live", label: "Live SDK stream active · HAM SSE" });
        } catch {
          /* noop */
        }
        return;
      }
      if (msg.event === "completed") setBanner({ phase: "ended", label: "Mission completed" });
      if (msg.event === "error")
        setBanner((b) =>
          b.phase !== "ended" && b.phase === "live"
            ? { phase: "reconnecting", label: "Reconnecting live feed…" }
            : b,
        );
    };

    const runLoop = async () => {
      let backoffMs = 900;
      let parsed: ReturnType<typeof feedSse>;
      outer: while (!cancelled && !isTerminalLive()) {
        const ac = new AbortController();
        sseAbortRef.current = ac;

        try {
          setBanner((b) =>
            b.phase === "ended" ? b : { phase: "connecting", label: "Connecting live mission feed…" },
          );

          const path = `/api/cursor/managed/missions/${encodeURIComponent(trimmed as string)}/feed/stream`;
          const qp =
            lastEventIdRef.current && lastEventIdRef.current.length
              ? `?after_event_id=${encodeURIComponent(lastEventIdRef.current)}`
              : "";
          const url = `${apiUrl(path)}${qp}`;
          const headers = new Headers();
          headers.set("Accept", "text/event-stream");
          await mergeClerkAuthBearerIfNeeded(headers);

          const res = await fetch(url, { credentials: "include", headers, signal: ac.signal });
          if (!res.ok || !res.body) throw new Error(`sse_http_${res.status}`);

          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let carry = "";
          backoffMs = 900;

          inner: while (!cancelled && !isTerminalLive()) {
            const { value, done } = await reader.read();
            if (done) {
              parsed = feedSse(carry, decoder.decode());
              carry = parsed.carry;
              for (const m of parsed.messages) applyMsg(m);
              break inner;
            }
            parsed = feedSse(carry, decoder.decode(value, { stream: true }));
            carry = parsed.carry;
            for (const m of parsed.messages) applyMsg(m);
          }

          if (cancelled || isTerminalLive()) break outer;

          setBanner({ phase: "reconnecting", label: "Reconnecting live feed…" });
          pollScheduleRef.current?.();
          await new Promise<void>((r) => setTimeout(r, backoffMs));
          backoffMs = Math.min(8500, Math.floor(backoffMs * 1.45));
          continue outer;
        } catch (e: unknown) {
          const abrt =
            (e instanceof DOMException && e.name === "AbortError") ||
            (e instanceof Error && e.name === "AbortError");
          if (cancelled || abrt) break outer;

          setBanner({ phase: "poll_only", label: "SDK stream unavailable — using REST refresh" });
          pollScheduleRef.current?.();
          await new Promise<void>((r) => setTimeout(r, Math.min(backoffMs * 2, 9500)));
          backoffMs = Math.min(8500, Math.floor(backoffMs * 1.55));
        }
      }
      sseAbortRef.current?.abort();
      sseAbortRef.current = null;
    };

    void runLoop();

    return () => {
      cancelled = true;
      sseAbortRef.current?.abort();
      sseAbortRef.current = null;
    };
  }, [trimmed, refreshSignal]);

  React.useEffect(() => {
    if (terminalFromFeed(feed)) {
      sseAbortRef.current?.abort();
      sseAbortRef.current = null;
    }
  }, [feed?.lifecycle]);

  const refetch = React.useCallback(async (): Promise<ManagedMissionFeedPayload | null> => {
    if (!trimmed) return null;
    const r = await fetchManagedMissionFeed(trimmed);
    const next = r.feed ?? null;
    setError(r.error ?? null);
    if (next) {
      latestFeedRef.current = next;
      setFeed(next);
      for (const ev of next.events) seenEventIdsRef.current.add(ev.id);
      const lid = sortEvents(next.events).at(-1)?.id;
      if (lid) lastEventIdRef.current = lid;
      if (terminalFromFeed(next)) setBanner({ phase: "ended", label: "Mission completed" });
    }
    setFirstPollDone(true);
    pollScheduleRef.current?.();
    return next;
  }, [trimmed]);

  const initialLoading = Boolean(trimmed) && !firstPollDone;

  return { feed, error, initialLoading, banner, refetch, feedScrollAnchorRef };
}
