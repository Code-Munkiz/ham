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
      status: "running" | "complete" | "error";
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

const REPEAT_SUFFIX = /\s*·\s*×(\d+)$/u;

function stripRepeatSuffix(label: string): string {
  return label.replace(REPEAT_SUFFIX, "").trim();
}

/**
 * Join two streamed text chunks without “glued words” at the boundary.
 * - If `next` starts with whitespace, append as-is (preserves newlines / intentional spacing).
 * - Do not insert a space before closing / attached punctuation at the start of `next`.
 * - Do not insert a space when `existing` ends with opening punctuation.
 * - Insert a single space between alphanumeric word boundaries when needed.
 */
export function joinTranscriptChunk(existing: string, next: string): string {
  if (!next) return existing;
  if (!existing) return next;
  if (/^\s/.test(next)) return existing + next;
  if (/\s$/.test(existing)) return existing + next;

  const last = existing.slice(-1);
  const first = next[0];
  if ("([{".includes(last)) return existing + next;
  if (/^[.,:;!?)\]}]/.test(next)) return existing + next;

  const prevWord = /[A-Za-z0-9_]$/.test(existing);
  const nextWord = /^[A-Za-z0-9_]/.test(next);
  if (prevWord && nextWord) return `${existing} ${next}`;

  if (/[.!?]$/.test(existing) && /^[A-Za-z]/.test(next)) return `${existing} ${next}`;

  return existing + next;
}

/** Heuristic repairs for common SDK token boundaries (after full chunk join). */
export function postJoinTranscriptText(text: string): string {
  let s = text;
  // "toimplement", "togather", … (see Cloud Agent stream screenshots)
  s = s.replace(
    /\bto(implement|implementing|gather|review|reviews|reviewing|determine|analyzes|analyse|analyze|integrate|integrating|complete|completing|establish|establishing|provide|providing|coordinate|coordinating|deploy|deploying|outline|outlining|migrate|migrating|recover|recovering|finalize|finalizing|focus|focuses|focused|outlines|outlined)\b/gi,
    (_m, verb: string) => `to ${String(verb).toLowerCase()}`,
  );
  const pairs: [RegExp, string][] = [
    [/\b(four)(roadmap)\b/gi, "$1 $2"],
    [/\b(on)(phases)\b/gi, "$1 $2"],
    [/\b(the)(observability)\b/gi, "$1 $2"],
    [/\b(honesty)(and)\b/gi, "$1 $2"],
    [/\b(phase)([a-z])\b/gi, "$1 $2"],
  ];
  for (const [re, rep] of pairs) {
    s = s.replace(re, rep);
  }
  return s;
}

/** Hide internal provider projection reason codes in the UI. */
export function formatTranscriptReasonCodeForDisplay(code: string | undefined | null): string | undefined {
  if (code == null) return undefined;
  const c = String(code).trim();
  if (!c) return undefined;
  if (/^cursor_typ:/i.test(c)) return undefined;
  if (/^cursor_sdk:/i.test(c)) return undefined;
  return c;
}

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
  const k = (ev.kind || "").trim();
  /** Flatten duplicate-looking provider_status labels */
  if (k.toLowerCase() === "provider_status" && msg) return msg.length > 120 ? `${msg.slice(0, 117)}…` : msg;
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

/** Collapse consecutive identical PROVIDER_STATUS / heartbeat-style rows into one transcript line with a repeat count. */
export function collapseAdjacentDuplicateTranscriptNoise(items: MissionTranscriptItem[]): MissionTranscriptItem[] {
  type Run =
    | { kind: "status"; base: MissionTranscriptItem & { type: "status" }; count: number }
    | { kind: "raw"; base: MissionTranscriptItem & { type: "raw" }; count: number };

  const fingerprint = (it: MissionTranscriptItem): string | null => {
    if (it.type === "status") {
      return `s:${stripRepeatSuffix(it.label).toLowerCase()}|${(it.reasonCode || "").toLowerCase()}`;
    }
    if (it.type === "raw") {
      const d = (it.detail || "").trim().toLowerCase();
      const lab = stripRepeatSuffix(it.label).trim().toLowerCase();
      return `r:${lab}|${d}`;
    }
    return null;
  }

  const finishRun = (run: Run | null): MissionTranscriptItem[] => {
    if (!run) return [];
    const { base, count } = run;
    if (count <= 1) return [base];
    const stripped = stripRepeatSuffix(base.label);
    const suffix = ` · ×${count}`;
    if (run.kind === "status") {
      return [{ ...base, label: `${stripped}${suffix}` }];
    }
    return [{ ...base, label: `${stripped}${suffix}` }];
  };

  const out: MissionTranscriptItem[] = [];
  let run: Run | null = null;

  const tryMerge = (it: MissionTranscriptItem) => {
    const fp = fingerprint(it);
    if (!fp) {
      out.push(...finishRun(run));
      run = null;
      out.push(it);
      return;
    }

    if (it.type === "status") {
      if (run?.kind !== "status" || fingerprint(run.base) !== fp) {
        out.push(...finishRun(run));
        run = { kind: "status", base: { ...it }, count: 1 };
        return;
      }
      run.count += 1;
      run.base = {
        ...run.base,
        time: it.time ?? run.base.time,
        eventIds: [...run.base.eventIds, ...it.eventIds],
      };
      return;
    }

    if (it.type === "raw") {
      if (run?.kind !== "raw" || fingerprint(run.base) !== fp) {
        out.push(...finishRun(run));
        run = { kind: "raw", base: { ...it }, count: 1 };
        return;
      }
      run.count += 1;
      run.base = {
        ...run.base,
        time: it.time ?? run.base.time,
        eventIds: [...run.base.eventIds, ...it.eventIds],
      };
      return;
    }

    out.push(...finishRun(run));
    run = null;
    out.push(it);
  };

  for (const it of items) tryMerge(it);
  out.push(...finishRun(run));
  return out;
}

/**
 * Build transcript blocks from the **full** bounded feed event list.
 * **Do not** slice `events` before calling — slice the returned array for display caps.
 *
 * Correct order elsewhere: ``buildMissionFeedTranscript`` → ``collapseAdjacentDuplicateTranscriptNoise`` → ``applyTranscriptStreamingHints`` → slice.
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
        text = joinTranscriptChunk(text, e.message || "");
        updatedAt = e.time;
        if (!reasonCode && e.reason_code) reasonCode = e.reason_code ?? undefined;
        i += 1;
      }
      out.push({
        type: "assistant",
        id: `assistant:${ids[0] ?? "na"}`,
        text: postJoinTranscriptText(text),
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
        text: postJoinTranscriptText(ev.message || ""),
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
        text = joinTranscriptChunk(text, e.message || "");
        updatedAt = e.time;
        i += 1;
      }
      out.push({
        type: "thinking",
        id: `thinking:${ids[0] ?? "na"}`,
        text: postJoinTranscriptText(text),
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
        text = joinTranscriptChunk(text, e.message || "");
        time = e.time;
        i += 1;
      }
      out.push({
        type: "user",
        id: `user:${ids[0] ?? "na"}`,
        text: postJoinTranscriptText(text),
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
      k === "provider_status" ||
      k === "artifact" ||
      k === "pr_url" ||
      k === "checkpoint" ||
      k === "mission_started"
    ) {
      let label = compactStatusLabel(ev);
      if (k === "provider_status" && !(ev.message || "").trim()) {
        label = "Provider status";
      }
      out.push({
        type: "status",
        id: `status:${ev.id}`,
        label,
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

/** Pipeline: ordered coalescing → status/raw de-duplication → streaming hints for the tail segment. */
export function missionFeedTranscriptFromEvents(
  events: ManagedMissionFeedEvent[],
  lifecycle: ManagedMissionLifecycle | null | undefined,
  bannerPhase: MissionFeedTranscriptBannerPhase,
): MissionTranscriptItem[] {
  const coalesced = buildMissionFeedTranscript(events);
  const collapsed = collapseAdjacentDuplicateTranscriptNoise(coalesced);
  return applyTranscriptStreamingHints(collapsed, lifecycle, bannerPhase);
}

/** Latest assistant text for Operations Outputs digest (truncated); uses finalized transcript rows. */
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
