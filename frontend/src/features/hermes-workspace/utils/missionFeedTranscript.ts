import type {
  ManagedMissionFeedEvent,
  ManagedMissionLifecycle,
} from "../adapters/managedMissionsAdapter";
import { isManagedMissionLifecycleTerminal } from "../adapters/managedMissionsAdapter";

export type MissionTranscriptItem =
  | {
      type: "assistant";
      id: string;
      text: string;
      startedAt?: string;
      updatedAt?: string;
      source?: string;
      reasonCode?: string;
      status?: "streaming" | "complete";
      eventIds: string[];
    }
  | {
      type: "thinking";
      id: string;
      text: string;
      startedAt?: string;
      updatedAt?: string;
      status?: "streaming" | "complete";
      eventIds: string[];
    }
  | {
      type: "tool";
      id: string;
      label: string;
      detail?: string;
      time?: string;
      status?: "running" | "complete" | "error";
      eventIds: string[];
    }
  | {
      type: "status";
      id: string;
      label: string;
      time?: string;
      reasonCode?: string;
      eventIds: string[];
    }
  | {
      type: "user";
      id: string;
      text: string;
      time?: string;
      eventIds: string[];
    }
  | {
      type: "raw";
      id: string;
      label: string;
      detail?: string;
      time?: string;
      eventIds: string[];
    };

function sortKey(ev: ManagedMissionFeedEvent): [string, string] {
  const t = (ev.time || "").trim() || "\uffff";
  return [t, ev.id || ""];
}

function sortedEvents(events: ManagedMissionFeedEvent[]): ManagedMissionFeedEvent[] {
  return [...events].sort((a, b) => {
    const [ta, ia] = sortKey(a);
    const [tb, ib] = sortKey(b);
    if (ta !== tb) return ta.localeCompare(tb);
    return ia.localeCompare(ib);
  });
}

function isCursorAssistant(ev: ManagedMissionFeedEvent): boolean {
  return ev.kind === "assistant_message" && String(ev.source || "").toLowerCase() === "cursor";
}

function consecutiveAssistant(ev: ManagedMissionFeedEvent, seedSource: string): boolean {
  return ev.kind === "assistant_message" && String(ev.source || "") === seedSource;
}

function isThinking(ev: ManagedMissionFeedEvent): boolean {
  return ev.kind === "thinking";
}

function isUserMessage(ev: ManagedMissionFeedEvent): boolean {
  return ev.kind === "user_message";
}

function isToolEvent(ev: ManagedMissionFeedEvent): boolean {
  return ev.kind === "tool_event";
}

function compactStatusLabel(ev: ManagedMissionFeedEvent): string {
  const msg = (ev.message || "").trim();
  if (msg) return msg.length > 120 ? `${msg.slice(0, 117)}…` : msg;
  return ev.kind || "Event";
}

function toolStatusFromEvent(ev: ManagedMissionFeedEvent): "running" | "complete" | "error" {
  const k = (ev.kind || "").toLowerCase();
  if (k === "error") return "error";
  return "complete";
}

/** Banner phase mirrors `ManagedMissionFeedStreamBanner` in the feed hook. */
export type MissionFeedTranscriptBannerPhase =
  | "idle"
  | "connecting"
  | "live"
  | "reconnecting"
  | "poll_only"
  | "ended";

/**
 * Build transcript blocks from the **full** bounded feed event list.
 * **Do not** slice `events` before calling — slice the returned array for display caps.
 */
export function buildMissionFeedTranscript(events: ManagedMissionFeedEvent[]): MissionTranscriptItem[] {
  const ordered = sortedEvents(events);
  const out: MissionTranscriptItem[] = [];

  let i = 0;
  while (i < ordered.length) {
    const ev = ordered[i];

    if (isCursorAssistant(ev)) {
      const src = String(ev.source || "");
      const ids: string[] = [];
      let text = "";
      let startedAt = ev.time;
      let updatedAt = ev.time;
      let source = ev.source;
      let reasonCode = ev.reason_code ?? undefined;
      while (i < ordered.length && consecutiveAssistant(ordered[i], src)) {
        const e = ordered[i];
        ids.push(e.id);
        text += e.message || "";
        updatedAt = e.time;
        if (!reasonCode && e.reason_code) reasonCode = e.reason_code ?? undefined;
        i += 1;
      }
      out.push({
        type: "assistant",
        id: `assistant:${ids[0] ?? "na"}`,
        text,
        startedAt,
        updatedAt,
        source,
        reasonCode,
        eventIds: ids,
      });
      continue;
    }

    /** Non-Cursor assistant_message: one block per event to avoid collapsing distinct sources. */
    if (ev.kind === "assistant_message") {
      out.push({
        type: "assistant",
        id: `assistant:${ev.id}`,
        text: ev.message || "",
        startedAt: ev.time,
        updatedAt: ev.time,
        source: ev.source,
        reasonCode: ev.reason_code ?? undefined,
        eventIds: [ev.id],
      });
      i += 1;
      continue;
    }

    if (isThinking(ev)) {
      const ids: string[] = [];
      let text = "";
      let startedAt = ev.time;
      let updatedAt = ev.time;
      while (i < ordered.length && isThinking(ordered[i])) {
        const e = ordered[i];
        ids.push(e.id);
        text += e.message || "";
        updatedAt = e.time;
        i += 1;
      }
      out.push({
        type: "thinking",
        id: `thinking:${ids[0] ?? "na"}`,
        text,
        startedAt,
        updatedAt,
        eventIds: ids,
      });
      continue;
    }

    if (isUserMessage(ev)) {
      const ids: string[] = [];
      let text = "";
      let time = ev.time;
      while (i < ordered.length && isUserMessage(ordered[i])) {
        const e = ordered[i];
        ids.push(e.id);
        text += e.message || "";
        time = e.time;
        i += 1;
      }
      out.push({
        type: "user",
        id: `user:${ids[0] ?? "na"}`,
        text,
        time,
        eventIds: ids,
      });
      continue;
    }

    if (isToolEvent(ev)) {
      out.push({
        type: "tool",
        id: `tool:${ev.id}`,
        label: (ev.message || "tool").trim() || "tool",
        detail: undefined,
        time: ev.time,
        status: toolStatusFromEvent(ev),
        eventIds: [ev.id],
      });
      i += 1;
      continue;
    }

    const k = (ev.kind || "").toLowerCase();
    if (
      k === "completed" ||
      k === "error" ||
      k === "status" ||
      k === "artifact" ||
      k === "pr_url" ||
      k === "checkpoint" ||
      k === "mission_started"
    ) {
      out.push({
        type: "status",
        id: `status:${ev.id}`,
        label: compactStatusLabel(ev),
        time: ev.time,
        reasonCode: ev.reason_code ?? undefined,
        eventIds: [ev.id],
      });
      i += 1;
      continue;
    }

    out.push({
      type: "raw",
      id: `raw:${ev.id}`,
      label: ev.kind || "event",
      detail: (ev.message || "").trim() || undefined,
      time: ev.time,
      eventIds: [ev.id],
    });
    i += 1;
  }

  return out;
}

/** Mark trailing assistant/thinking segment as streaming while the mission stays active. */
export function applyTranscriptStreamingHints(
  items: MissionTranscriptItem[],
  lifecycle: ManagedMissionLifecycle | null | undefined,
  bannerPhase: MissionFeedTranscriptBannerPhase,
): MissionTranscriptItem[] {
  const base = items.map((it) => ({ ...it }));
  const terminal = lifecycle ? isManagedMissionLifecycleTerminal(lifecycle) : false;
  const lastIdx = base.length - 1;
  /** ``idle``: before first ingest — avoid falsely marking the transcript tail as actively streaming. */
  if (lastIdx < 0 || terminal || bannerPhase === "ended" || bannerPhase === "idle") {
    return base.map((it) => {
      if (it.type === "assistant" || it.type === "thinking") {
        return { ...it, status: "complete" as const };
      }
      return it;
    });
  }

  const tail = base[lastIdx];
  if (tail.type !== "assistant" && tail.type !== "thinking") {
    return base.map((it) => {
      if (it.type === "assistant" || it.type === "thinking") return { ...it, status: "complete" as const };
      return it;
    });
  }

  return base.map((it, idx) => {
    if (it.type !== "assistant" && it.type !== "thinking") return it;
    return idx === lastIdx ? { ...it, status: "streaming" as const } : { ...it, status: "complete" as const };
  });
}

/** Latest assistant text for Operations Outputs digest (truncated). */
export function latestAssistantPreviewFromTranscript(items: MissionTranscriptItem[], maxLen = 800): string | null {
  for (let i = items.length - 1; i >= 0; i--) {
    const it = items[i];
    if (it.type !== "assistant") continue;
    const t = it.text.trim();
    if (!t) continue;
    if (t.length <= maxLen) return t;
    return `${t.slice(0, maxLen - 1)}…`;
  }
  return null;
}
