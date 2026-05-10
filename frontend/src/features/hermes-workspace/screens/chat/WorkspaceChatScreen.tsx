/**
 * Workspace-native chat: upstream Hermes `ChatScreen` visual/IA pattern, HAM `/api/chat/stream` only.
 * Each stream POST sends one new user turn plus `session_id`; prior transcript is not re-sent (privacy + payload size).
 * Hermes Workspace chat only (no legacy workbench chrome).
 */

import * as React from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ExternalLink, Loader2, PanelRight, PanelRightClose } from "lucide-react";
import { toast } from "sonner";
import {
  appendChatSessionTurns,
  createChatSession,
  downloadChatSessionPdf,
  ensureProjectIdForWorkspaceRoot,
  fetchChatComposerPreference,
  fetchChatCapabilities,
  fetchChatContextMeters,
  fetchContextEngine,
  fetchHamGeneratedMediaBlob,
  fetchHamGeneratedMediaMeta,
  fetchHamMediaJobStatus,
  fetchModelsCatalog,
  HamAccessRestrictedError,
  HamChatStreamIncompleteError,
  putChatComposerPreference,
  postChatTranscribe,
  postChatUploadAttachment,
  postHamGeneratedImage,
  postHamGeneratedVideo,
  type HamChatExecutionMode,
} from "@/lib/ham/api";
import { CLIENT_MODEL_CATALOG_FALLBACK } from "@/lib/ham/modelCatalogFallback";
import type {
  ChatCapabilitiesPayload,
  ChatContextMetersPayload,
  ModelCatalogPayload,
} from "@/lib/ham/types";
import { applyHamUiActions } from "@/lib/ham/applyUiActions";
import type { HamChatStreamAuth } from "@/lib/ham/api";
import type { HamChatUserContentV1, HamChatUserContentV2 } from "@/lib/ham/chatUserContent";
import { useHamWorkspace } from "@/lib/ham/HamWorkspaceContext";
import {
  buildHamChatUserPayloadV1,
  buildHamChatUserPayloadV2,
  userTranscriptPreview,
} from "@/lib/ham/chatUserContent";
import { workspaceChatAdapter, workspaceSessionAdapter } from "../../workspaceAdapters";
import {
  fetchManagedMissionDetail,
  postManagedMissionMessage,
  type ManagedMissionSnapshot,
} from "../../adapters/managedMissionsAdapter";
import { useManagedMissionFeedLiveStream } from "../../hooks/useManagedMissionFeedLiveStream";
import { cursorCloudAgentWebHref, isBcCursorAgentId } from "../../utils/cursorCloudAgentWeb";
import {
  formatTranscriptReasonCodeForDisplay,
  missionFeedTranscriptFromEvents,
  type MissionTranscriptItem,
} from "../../utils/missionFeedTranscript";
import { MANAGED_MISSION_CHAT_OWNERSHIP_HINT } from "../../lib/managedMissionOwnershipCopy";
import { useVoiceWorkspaceSettingsOptional } from "../../voice/VoiceWorkspaceSettingsContext";
import { WorkspaceChatEmptyState, WORKSPACE_CHAT_SUGGESTIONS } from "./WorkspaceChatEmptyState";
import { WorkspaceChatMessageList, type HwwMsgRow } from "./WorkspaceChatMessageList";
import { WorkspaceChatComposer } from "./WorkspaceChatComposer";
import type {
  ComposerExportPdfState,
  ComposerGenerateImageState,
  ComposerGenerateVideoState,
} from "./WorkspaceChatComposerActionsMenu";
import {
  parseWorkspaceCreativeImageIntent,
  parseWorkspaceImageGenerationIntent,
} from "./imageGenerationIntent";
import { useWorkspaceHamProject } from "../../WorkspaceHamProjectContext";
import { WorkspaceChatInspectorPanel } from "./WorkspaceChatInspectorPanel";
import { WorkspaceWorkbench } from "../../workbench/WorkspaceWorkbench";
import {
  appendInspectorEvent,
  patchInspectorEventsSessionId,
  safeInspectorErrorMessage,
  type WorkspaceInspectorEvent,
} from "./workspaceInspectorEvents";
import {
  mergeArtifactRowsAfterTurn,
  type ChatInspectorArtifactRow,
} from "./workspaceInspectorChatDerived";
import {
  buildFileForServerUpload,
  fileToWorkspaceAttachment,
  formatAttachmentByteSize,
  MAX_WORKSPACE_ATTACHMENT_COUNT,
  MAX_WORKSPACE_DOCUMENT_BYTES,
  MAX_WORKSPACE_IMAGE_BYTES,
  revokeWorkspaceComposerAttachmentPreviews,
  type WorkspaceComposerAttachment,
} from "./composerAttachmentHelpers";
import { Button } from "@/components/ui/button";
import { hamWorkspaceLogoUrl } from "@/lib/ham/publicAssets";
import { cn } from "@/lib/utils";
import { isHamDesktopShell } from "@/lib/ham/desktopConfig";
import {
  getHamDesktopLocalControlApi,
  getHamDesktopWebBridgeApi,
} from "@/lib/ham/desktopBundleBridge";
import {
  readWorkspaceLastChatSessionId,
  writeWorkspaceLastChatSessionId,
} from "./workspaceChatSessionStorage";

function mapServerAttachmentKind(serverKind: string): WorkspaceComposerAttachment["kind"] {
  if (serverKind === "image") return "image";
  if (serverKind === "video") return "video";
  return "file";
}

const VOICE_DEBUG_FLAG = "ham.voiceDebug";

/** Desktop `/workspace/chat`: command column width (px) vs workbench — drag + `localStorage`. */
const HWW_CHAT_CMD_PANEL_LS_KEY = "hww.workbench.commandPanelWidth";
const HWW_CHAT_CMD_PANEL_DEFAULT_PX = 480;
const HWW_CHAT_CMD_PANEL_MIN_PX = 360;
const HWW_CHAT_CMD_PANEL_MAX_PX = 720;
const HWW_WORKBENCH_PANEL_MIN_PX = 420;
const HWW_CHAT_SPLIT_RESIZER_PX = 6;

function voiceDebugEnabled(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(VOICE_DEBUG_FLAG) === "1";
  } catch {
    return false;
  }
}

function pushVoiceDebug(payload: Record<string, unknown>): void {
  if (!voiceDebugEnabled() || typeof window === "undefined") return;
  const event = { ...payload, ts: Date.now() };
  const w = window as unknown as { __HAM_VOICE_DEBUG__?: Array<Record<string, unknown>> };
  const arr = Array.isArray(w.__HAM_VOICE_DEBUG__) ? [...w.__HAM_VOICE_DEBUG__, event] : [event];
  if (arr.length > 500) arr.splice(0, arr.length - 500);
  w.__HAM_VOICE_DEBUG__ = arr;
  console.debug("[ham.voice]", event);
}

function timeStr() {
  return new Date().toLocaleTimeString([], {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/**
 * True → composer Send should call the async video pipeline instead of /api/chat (text-only submits).
 * - Mock gateway (local POC): every non-empty prompt is treated as video so Send matches + → Generate video.
 * - Real gateway: only obvious video phrasing avoids hijacking normal chat.
 */
function shouldEnqueueVideoOnComposerSend(opts: {
  trimmed: string;
  supportsVideo: boolean;
  gatewayMode: string | null | undefined;
}): boolean {
  const t = opts.trimmed.trim();
  if (!t || !opts.supportsVideo) return false;
  const gm = (opts.gatewayMode || "").trim().toLowerCase();
  if (gm === "mock") return true;
  return (
    /\b(video|videos|videoclip|clip|clips|gif|animate|animation|animated|movie|film|footage|cinematic)\b/i.test(
      t,
    ) ||
    /\b\d+\s*(sec|secs|second|seconds)\b/i.test(t) ||
    /^(make|create|render)\s+/i.test(t) ||
    /\b(generate|generating)\s+\w*\s*\b(video|clip|animation)\b/i.test(t) ||
    /\b(video|clip|animation)\b.*\b(of|showing|about)\b/i.test(t)
  );
}

function shortId(v: string | null | undefined): string {
  const s = String(v || "").trim();
  if (!s) return "—";
  if (s.length <= 16) return s;
  return `${s.slice(0, 8)}…${s.slice(-6)}`;
}

/** Space after `:` when the API sends `mapped:FINISHED`-style tokens (e.g. `mapped: FINISHED`). */
function formatMissionStatusTitleForDisplay(title: string): string {
  return title.replace(/:([A-Z])/g, ": $1");
}

function revokeGeneratedMediaBlobUrlsFromMessages(rows: readonly HwwMsgRow[]): void {
  for (const m of rows) {
    const cards = [m.generatedImageCard, m.generatedVideoCard];
    for (const c of cards) {
      if (c?.kind === "ready" && typeof c.blobUrl === "string" && c.blobUrl.startsWith("blob:")) {
        URL.revokeObjectURL(c.blobUrl);
      }
    }
  }
}

async function waitMs(ms: number): Promise<void> {
  await new Promise((resolve) => window.setTimeout(resolve, ms));
}

function fmtMissionFeedIsoBrief(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return iso;
  return new Date(t).toLocaleString([], {
    hour12: false,
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ChatThinkingTranscriptChunk({
  item,
}: {
  item: Extract<MissionTranscriptItem, { type: "thinking" }>;
}) {
  const [open, setOpen] = React.useState(false);
  const long = (item.text || "").length > 200;
  if (!long) {
    return (
      <div className="rounded border border-white/[0.06] bg-white/[0.03] px-2 py-1">
        <p className="whitespace-pre-wrap text-[11px] leading-relaxed text-white/55">{item.text}</p>
      </div>
    );
  }
  return (
    <div className="rounded border border-white/[0.06] bg-white/[0.03] px-2 py-1">
      <button
        type="button"
        className="w-full text-left text-[10px] font-medium uppercase tracking-wider text-white/40"
        onClick={() => setOpen((x) => !x)}
      >
        Thinking{item.status === "streaming" ? " (streaming)" : ""} · {open ? "hide" : "show"}
      </button>
      {open ? (
        <p className="mt-1 whitespace-pre-wrap text-[11px] leading-relaxed text-white/55">
          {item.text}
        </p>
      ) : (
        <p className="mt-1 truncate text-[11px] text-white/45">
          {item.text.length <= 120 ? item.text : `${item.text.slice(0, 120)}…`}
        </p>
      )}
    </div>
  );
}

function ChatMissionFeedTranscript({
  items,
  anchorRef,
}: {
  items: MissionTranscriptItem[];
  anchorRef: React.RefObject<HTMLDivElement | null>;
}) {
  return (
    <div className="space-y-1.5">
      {items.map((block) => {
        if (block.type === "assistant") {
          const rcDisp = formatTranscriptReasonCodeForDisplay(block.reasonCode);
          return (
            <div
              key={block.id}
              className="rounded border border-white/[0.06] bg-white/[0.03] px-2 py-1.5"
            >
              <p className="whitespace-pre-wrap text-[12px] leading-snug text-white/[0.88]">
                {block.text}
              </p>
              <p className="mt-0.5 text-[10px] leading-relaxed text-white/40">
                {fmtMissionFeedIsoBrief(block.updatedAt)}
                {rcDisp ? ` · ${rcDisp}` : ""}
                {block.status === "streaming" ? " · streaming…" : ""}
              </p>
            </div>
          );
        }
        if (block.type === "thinking")
          return <ChatThinkingTranscriptChunk key={block.id} item={block} />;
        if (block.type === "user") {
          return (
            <div
              key={block.id}
              className="rounded border border-white/[0.06] bg-white/[0.04] px-2 py-1"
            >
              <p className="whitespace-pre-wrap text-[11px] leading-relaxed text-white/[0.85]">
                {block.text}
              </p>
              <p className="mt-0.5 text-[10px] leading-relaxed text-white/40">
                {fmtMissionFeedIsoBrief(block.time)} · user
              </p>
            </div>
          );
        }
        if (block.type === "tool") {
          return (
            <div
              key={block.id}
              className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 border-b border-white/[0.06] py-0.5 font-mono text-[10px] text-white/50"
            >
              <span className="text-white/35">tool</span>
              <span className="font-sans text-white/65">{block.label}</span>
              {block.time ? (
                <span className="ml-auto text-white/30">{fmtMissionFeedIsoBrief(block.time)}</span>
              ) : null}
            </div>
          );
        }
        if (block.type === "status") {
          const rcDisp = formatTranscriptReasonCodeForDisplay(block.reasonCode);
          return (
            <div key={block.id} className="flex flex-wrap gap-x-2 text-[10px] text-white/45">
              <span className="text-white/60">{block.label}</span>
              {block.time ? (
                <span className="text-white/30">{fmtMissionFeedIsoBrief(block.time)}</span>
              ) : null}
              {rcDisp ? <span className="font-mono text-white/30">{rcDisp}</span> : null}
            </div>
          );
        }
        return (
          <div key={block.id} className="flex flex-wrap gap-x-2 text-[10px] text-white/38">
            <span className="font-mono uppercase tracking-wider text-white/30">{block.label}</span>
            {block.detail ? <span className="text-white/55">{block.detail}</span> : null}
          </div>
        );
      })}
      <div ref={anchorRef} className="h-px w-full" aria-hidden />
    </div>
  );
}

function workspaceChatSubtitle(opts: {
  sessionLoadFailed: boolean;
  staleSessionParam: string | null;
  sessionId: string | null;
  messages: HwwMsgRow[];
}): string {
  if (opts.sessionLoadFailed && opts.staleSessionParam) {
    return "This link may be expired or the chat was removed. Start a new chat or pick one from the sidebar.";
  }
  if (opts.sessionId) {
    const firstUser = opts.messages.find((m) => m.role === "user");
    const raw = firstUser?.content;
    const preview = typeof raw === "string" ? userTranscriptPreview(raw) : "";
    if (preview) {
      const oneLine = preview.replace(/\s+/g, " ");
      return oneLine.length > 72 ? `${oneLine.slice(0, 72)}…` : oneLine;
    }
    return "Send a message to start this conversation.";
  }
  return "Messages you send are stored by HAM after the first reply.";
}

function extractFirstUrl(text: string): string | null {
  const raw = text.match(/\b((?:https?:\/\/|www\.)[^\s]+)/i)?.[1];
  if (!raw) return null;
  const candidate = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
  try {
    const u = new URL(candidate);
    if (u.protocol !== "http:" && u.protocol !== "https:") return null;
    return u.toString();
  } catch {
    return null;
  }
}

function isLikelyBrowserTask(text: string): boolean {
  const t = text.trim().toLowerCase();
  if (!t) return false;
  if (extractFirstUrl(t)) return true;
  const patterns = [
    /\bopen\b.*\b(browser|site|page|web)\b/,
    /\b(go to|visit|navigate to|open)\b/,
    /\b(search|look up|lookup|find)\b/,
    /\b(click|scroll|type|press|wait|what do you see|what do you notice|read this page)\b/,
  ];
  return patterns.some((p) => p.test(t));
}

function isFollowUpBrowserInstruction(text: string): boolean {
  const t = text.trim().toLowerCase();
  if (!t) return false;
  return /\b(click|scroll|type|select|open that|what do you see|what does this page|read the page)\b/.test(
    t,
  );
}

function buildSafeSearchUrl(text: string): string {
  const q = text
    .replace(/\b(open|browser|search|look up|lookup|find|for me|please)\b/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
  return `https://duckduckgo.com/?q=${encodeURIComponent(q || text.trim())}`;
}

function missionFollowupMessageForReason(reasonCode: string | null, ok: boolean): string {
  if (ok) return "Instruction recorded for this mission and sent to the provider.";
  switch (reasonCode) {
    case "mission_not_active":
      return "This mission is not active anymore, so follow-up instructions cannot be sent.";
    case "mission_not_found":
      return "I could not find that mission.";
    case "mission_followup_not_supported":
      return "This provider does not support mission follow-up yet. I still recorded your instruction in the mission feed.";
    case "provider_followup_not_supported":
      return "Provider follow-up is unavailable right now. I still recorded your instruction in the mission feed.";
    default:
      return "I could not send that follow-up right now. Your instruction was recorded in the mission feed.";
  }
}

function localBrowserFailureMessage(reason: string): string {
  switch (reason) {
    case "bridge_disabled":
      return "Local bridge unavailable: GOHAM is disabled in desktop settings.";
    case "token_missing":
    case "token_invalid":
    case "token_expired":
    case "token_revoked":
      return "Connect GOHAM first, then retry this browser task.";
    case "real_browser_automation_off":
      return "Local control is not armed yet. Enable browser control, then retry.";
    case "url_policy_blocked":
      return "That URL is blocked by local browser safety policy.";
    case "browser_not_found":
      return "Local browser executable was not found on this machine.";
    case "bridge_start_failed":
      return "Local bridge could not start. Reopen GOHAM and retry.";
    case "selector_invalid":
    case "field_not_allowed":
    case "field_blocked":
      return "That field is not allowed for live typing. Pick a visible safe text field.";
    case "key_not_allowed":
      return "That key is blocked in Copilot v1. Use navigation keys only.";
    case "wait_out_of_range":
      return "Wait must be between 0.5 and 3 seconds in Copilot v1.";
    case "unknown_candidate_id":
    case "candidates_stale":
      return "I need a fresh page observe before clicking. Ask me to observe, then click.";
    default:
      return `Local browser handoff failed (${reason || "unknown_error"}).`;
  }
}

type LocalCopilotPrimitiveIntent =
  | { action: "blocked_coordinate" }
  | { action: "observe" }
  | { action: "scroll"; delta_y: number }
  | { action: "wait"; wait_ms: number }
  | { action: "key_press"; key: string }
  | { action: "type_into_field"; selector: string; text: string }
  | { action: "click_candidate"; ordinal: number };

function parseLocalCopilotPrimitive(text: string): LocalCopilotPrimitiveIntent | null {
  const t = text.trim();
  const lower = t.toLowerCase();
  if (!lower) return null;
  if (/\b(observe|what do you see|what's on the page|read this page)\b/.test(lower))
    return { action: "observe" };
  const waitMatch =
    /\bwait\s+(\d+(?:\.\d+)?)\s*(ms|millisecond|milliseconds|s|sec|secs|second|seconds)?\b/i.exec(
      t,
    );
  if (waitMatch) {
    const amount = Number(waitMatch[1] || "0");
    const unit = String(waitMatch[2] || "s").toLowerCase();
    const waitMs = /ms|millisecond/.test(unit) ? Math.round(amount) : Math.round(amount * 1000);
    return { action: "wait", wait_ms: waitMs };
  }
  if (/\bscroll\b/.test(lower)) {
    const amount = Number((/\b(\d{2,4})\b/.exec(lower)?.[1] ?? "420").trim());
    const dir = /\b(up|top)\b/.test(lower) ? -1 : 1;
    return { action: "scroll", delta_y: Math.max(120, Math.min(600, amount)) * dir };
  }
  if (/\b(click|tap)\b.*\b(x|y)\s*[:=]?\s*\d+\b/.test(lower) || /\bcoordinates?\b/.test(lower)) {
    return { action: "blocked_coordinate" };
  }
  const pressMatch = /\bpress\s+([a-z ]{2,20})\b/i.exec(t);
  if (pressMatch) {
    const raw = String(pressMatch[1] || "").toLowerCase();
    const keyMap: Record<string, string> = {
      tab: "Tab",
      escape: "Escape",
      up: "ArrowUp",
      down: "ArrowDown",
      left: "ArrowLeft",
      right: "ArrowRight",
      "page up": "PageUp",
      "page down": "PageDown",
      home: "Home",
      end: "End",
    };
    return { action: "key_press", key: keyMap[raw] || raw.replace(/\s+/g, " ") };
  }
  const typeIntoMatch = /\btype\s+(.+?)\s+into\s+(.+)$/i.exec(t);
  if (typeIntoMatch) {
    const targetRaw = String(typeIntoMatch[2] || "")
      .trim()
      .toLowerCase();
    const defaultSearchSelector =
      'input[type="search"],input[name*="search" i],input[aria-label*="search" i],input[name="q" i],input[id*="search" i],textarea';
    const normalizedSelector = /\b(search|search box|search field)\b/.test(targetRaw)
      ? defaultSearchSelector
      : targetRaw;
    return {
      action: "type_into_field",
      text: String(typeIntoMatch[1] || "")
        .trim()
        .replace(/^["']|["']$/g, ""),
      selector: normalizedSelector,
    };
  }
  const typeMatch = /\btype\s+(.+)$/i.exec(t);
  if (typeMatch) {
    return {
      action: "type_into_field",
      text: String(typeMatch[1] || "")
        .trim()
        .replace(/^["']|["']$/g, ""),
      selector:
        'input[type="search"],input[name*="search" i],input[aria-label*="search" i],input[name="q" i],input[id*="search" i],textarea',
    };
  }
  const clickMatch = /\bclick(?:\s+the)?\s*(first|second|third|fourth|\d+)?/i.exec(t);
  if (clickMatch) {
    const raw = String(clickMatch[1] || "first").toLowerCase();
    const n =
      raw === "first"
        ? 1
        : raw === "second"
          ? 2
          : raw === "third"
            ? 3
            : raw === "fourth"
              ? 4
              : Number(raw);
    return { action: "click_candidate", ordinal: Number.isFinite(n) && n > 0 ? n : 1 };
  }
  return null;
}

export type WorkspaceChatScreenProps = {
  /** In-shell drawer: keep session off the URL; do not navigate on new session. */
  embedMode?: boolean;
};

export function WorkspaceChatScreen(props: WorkspaceChatScreenProps = {}) {
  const { embedMode = false } = props;
  const { setHamProjectId } = useWorkspaceHamProject();
  const hamWorkspace = useHamWorkspace();
  const navigate = useNavigate();
  const desktopShell = isHamDesktopShell();
  const executionEnvironment: "desktop" | "web" = desktopShell ? "desktop" : "web";
  const chatScreenInstanceId = React.useRef(
    `chat-screen-${Math.random().toString(36).slice(2, 9)}`,
  );
  const [searchParams] = useSearchParams();
  const missionIdFromQuery = embedMode
    ? null
    : (searchParams.get("mission_id") || "").trim() || null;
  const {
    feed: missionFeed,
    refetch: refetchMissionFeed,
    banner: missionFeedBanner,
    initialLoading: missionFeedInitialLoading,
    feedScrollAnchorRef: missionFeedScrollAnchorRef,
  } = useManagedMissionFeedLiveStream(missionIdFromQuery);

  const displayedMissionFeedTranscript = React.useMemo(() => {
    const ev = missionFeed?.events ?? [];
    return missionFeedTranscriptFromEvents(
      ev,
      missionFeed?.lifecycle ?? null,
      missionFeedBanner.phase,
    ).slice(-5);
  }, [missionFeed?.events, missionFeed?.lifecycle, missionFeedBanner.phase]);
  const activeWorkspaceId =
    hamWorkspace.state.status === "ready" ? hamWorkspace.state.activeWorkspaceId : null;
  const workspaceRestoreScope = activeWorkspaceId?.trim() || "__legacy__";

  const [messages, setMessages] = React.useState<HwwMsgRow[]>([]);
  const [sessionId, setSessionId] = React.useState<string | null>(null);
  const [input, setInput] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const [loadErr, setLoadErr] = React.useState<string | null>(null);
  const [loadingSession, setLoadingSession] = React.useState(false);
  const [catalog, setCatalog] = React.useState<ModelCatalogPayload | null>(null);
  const [catalogLoading, setCatalogLoading] = React.useState(true);
  const [missionContext, setMissionContext] = React.useState<ManagedMissionSnapshot | null>(null);
  const [missionLoading, setMissionLoading] = React.useState(false);
  const [missionError, setMissionError] = React.useState<string | null>(null);
  const [modelId, setModelId] = React.useState<string | null>(null);
  const [failedChatModelIds, setFailedChatModelIds] = React.useState<string[]>([]);
  const executionModePreference: "auto" | "browser" | "machine" | "chat" = "auto";
  const [executionMode, setExecutionMode] = React.useState<HamChatExecutionMode | null>(null);
  const [projectId, setProjectId] = React.useState<string | null>(null);
  const [attachments, setAttachments] = React.useState<WorkspaceComposerAttachment[]>([]);
  const attachmentsRef = React.useRef(attachments);
  React.useEffect(() => {
    attachmentsRef.current = attachments;
  }, [attachments]);

  const [voiceTranscribing, setVoiceTranscribing] = React.useState(false);
  const chatSplitRowRef = React.useRef<HTMLDivElement | null>(null);
  const cmdPanelWidthPxRef = React.useRef(HWW_CHAT_CMD_PANEL_DEFAULT_PX);
  const [cmdPanelWidthPx, setCmdPanelWidthPx] = React.useState(HWW_CHAT_CMD_PANEL_DEFAULT_PX);
  cmdPanelWidthPxRef.current = cmdPanelWidthPx;
  const splitDragRef = React.useRef<{ startX: number; startW: number } | null>(null);
  const [splitResizePointerDown, setSplitResizePointerDown] = React.useState(false);
  const [isDesktopSplitLayout, setIsDesktopSplitLayout] = React.useState(false);

  const [inspectorOpen, setInspectorOpen] = React.useState(false);
  const [pdfExporting, setPdfExporting] = React.useState(false);
  const [chatCapabilities, setChatCapabilities] = React.useState<ChatCapabilitiesPayload | null>(
    null,
  );
  const [chatCapabilitiesLoading, setChatCapabilitiesLoading] = React.useState(true);
  const [contextMetersPayload, setContextMetersPayload] =
    React.useState<ChatContextMetersPayload | null>(null);
  const [imageGenInFlight, setImageGenInFlight] = React.useState(false);
  const [videoGenInFlight, setVideoGenInFlight] = React.useState(false);
  const [inspectorEvents, setInspectorEvents] = React.useState<WorkspaceInspectorEvent[]>([]);
  const [artifactRows, setArtifactRows] = React.useState<ChatInspectorArtifactRow[]>([]);
  /** Desktop GOHAM web bridge: trusted session is main-process only; this tracks UI + follow-up routing. */
  const desktopWebBridgeTrustedRef = React.useRef(false);
  /** After a turn used browser execution, follow-up plain text can stay on current screen (desktop + trusted bridge). */
  const browserSessionFollowThroughRef = React.useRef(false);
  const liveCopilotCandidatesRef = React.useRef<Array<{ id: string }>>([]);
  const [gohamModalOpen, setGohamModalOpen] = React.useState(false);
  const [gohamBridgeLinked, setGohamBridgeLinked] = React.useState(false);
  const [gohamModalPhase, setGohamModalPhase] = React.useState<
    "idle" | "checking" | "connecting" | "connected" | "blocked" | "failed"
  >("idle");
  const [gohamModalDetail, setGohamModalDetail] = React.useState<string | null>(null);
  const [gohamBridgeExplicitlyDisabled, setGohamBridgeExplicitlyDisabled] = React.useState(false);
  /** When set, deep-link effect must not call `loadFromApi` for this session while the stream turn is active. */
  const streamTurnSessionRef = React.useRef<string | null>(null);
  const lastSessionRestoreScopeRef = React.useRef<string | null>(null);
  const endRef = React.useRef<HTMLDivElement | null>(null);
  const chatAttachmentLocalBlobByServerIdRef = React.useRef<Map<string, string>>(new Map());
  const listWrapRef = React.useRef<HTMLDivElement | null>(null);
  /** Last session id successfully fetched via `loadFromApi` — used to avoid revoking same-tab attachment blob cache on refresh. */
  const previousLoadedWorkspaceSessionRef = React.useRef<string | null>(null);
  const activeWorkspaceIdRef = React.useRef(activeWorkspaceId);
  const previousActiveWorkspaceIdRef = React.useRef<string | null | undefined>(undefined);
  /**
   * Workspace switch schedules `navigate({ search: "" })`, but `useSearchParams` in that same
   * commit still reflects the pre-navigation URL. Skip `?session=` deep-link loads until the
   * param clears so a prior workspace's session id is not fetched under the new workspace
   * (404 / "Session unavailable" after create/switch).
   */
  const suppressSessionQueryUntilNavigationRef = React.useRef(false);

  const clampCmdPanelWidthPx = React.useCallback((w: number) => {
    const clampedBase = Math.min(HWW_CHAT_CMD_PANEL_MAX_PX, Math.max(HWW_CHAT_CMD_PANEL_MIN_PX, w));
    const row = chatSplitRowRef.current;
    if (!row) return clampedBase;
    const total = row.getBoundingClientRect().width;
    if (total <= 0) return clampedBase;
    const maxFromBench = total - HWW_WORKBENCH_PANEL_MIN_PX - HWW_CHAT_SPLIT_RESIZER_PX;
    const ceiling = Math.min(
      HWW_CHAT_CMD_PANEL_MAX_PX,
      Math.max(HWW_CHAT_CMD_PANEL_MIN_PX, maxFromBench),
    );
    return Math.min(clampedBase, ceiling);
  }, []);

  React.useEffect(() => {
    try {
      const raw = localStorage.getItem(HWW_CHAT_CMD_PANEL_LS_KEY);
      if (raw) {
        const n = Number.parseInt(raw, 10);
        if (Number.isFinite(n)) {
          setCmdPanelWidthPx(
            Math.min(HWW_CHAT_CMD_PANEL_MAX_PX, Math.max(HWW_CHAT_CMD_PANEL_MIN_PX, n)),
          );
        }
      }
    } catch {
      /* ignore */
    }
  }, []);

  React.useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    const sync = () => {
      setIsDesktopSplitLayout(mq.matches);
    };
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  React.useEffect(() => {
    if (!isDesktopSplitLayout) return;
    setCmdPanelWidthPx((prev) => clampCmdPanelWidthPx(prev));
  }, [isDesktopSplitLayout, clampCmdPanelWidthPx]);

  React.useEffect(() => {
    if (!isDesktopSplitLayout) return;
    const onResize = () => {
      setCmdPanelWidthPx((prev) => clampCmdPanelWidthPx(prev));
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [isDesktopSplitLayout, clampCmdPanelWidthPx]);

  React.useEffect(() => {
    if (!splitResizePointerDown) return;
    const onMove = (e: PointerEvent) => {
      const d = splitDragRef.current;
      if (!d) return;
      setCmdPanelWidthPx(clampCmdPanelWidthPx(d.startW + (e.clientX - d.startX)));
    };
    const onUp = () => {
      splitDragRef.current = null;
      setSplitResizePointerDown(false);
      try {
        localStorage.setItem(HWW_CHAT_CMD_PANEL_LS_KEY, String(cmdPanelWidthPxRef.current));
      } catch {
        /* ignore */
      }
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
  }, [splitResizePointerDown, clampCmdPanelWidthPx]);

  React.useEffect(() => {
    activeWorkspaceIdRef.current = activeWorkspaceId;
  }, [activeWorkspaceId]);

  const composerPrefSaveTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelComposerPrefSaveTimer = React.useCallback(() => {
    if (composerPrefSaveTimerRef.current !== null) {
      clearTimeout(composerPrefSaveTimerRef.current);
      composerPrefSaveTimerRef.current = null;
    }
  }, []);

  const revokeAllChatAttachmentLocalBlobs = React.useCallback(() => {
    for (const u of chatAttachmentLocalBlobByServerIdRef.current.values()) {
      try {
        URL.revokeObjectURL(u);
      } catch {
        /* ignore */
      }
    }
    chatAttachmentLocalBlobByServerIdRef.current.clear();
  }, []);

  const stashImageBlobsForServerIdsBeforeSend = React.useCallback(
    async (rows: WorkspaceComposerAttachment[]) => {
      await Promise.all(
        rows.map(async (a) => {
          if (a.kind !== "image" || !a.serverId || !(a.payload || "").startsWith("blob:")) return;
          try {
            const blob = await (await fetch(a.payload)).blob();
            const u = URL.createObjectURL(blob);
            const old = chatAttachmentLocalBlobByServerIdRef.current.get(a.serverId);
            if (old && old !== u) {
              try {
                URL.revokeObjectURL(old);
              } catch {
                /* ignore */
              }
            }
            chatAttachmentLocalBlobByServerIdRef.current.set(a.serverId, u);
          } catch {
            /* GET fallback via WorkspaceChatAuthImage */
          }
        }),
      );
    },
    [],
  );

  const voiceWs = useVoiceWorkspaceSettingsOptional();
  const sttEnabledBySetting = voiceWs?.payload?.settings.stt.enabled ?? true;
  const sttMode = voiceWs?.payload?.settings.stt.mode ?? "record";
  const sttRuntimeAvailable = voiceWs?.payload?.capabilities.stt.available ?? true;
  const sttDictationEnabled = sttEnabledBySetting && (sttMode !== "record" || sttRuntimeAvailable);
  const sttUnavailableReason = !sttEnabledBySetting
    ? "Speech-to-text is off — enable it in Workspace → Settings → Voice."
    : sttMode === "record" && !sttRuntimeAvailable
      ? "Speech-to-text is not configured on this HAM API host."
      : null;

  const handleSttModeChange = React.useCallback(
    async (mode: "auto" | "live" | "record") => {
      if (!voiceWs) return;
      await voiceWs.updateVoiceSettings({ stt: { mode } });
    },
    [voiceWs],
  );

  const refreshGohamBridgeLinked = React.useCallback(async () => {
    const api = getHamDesktopWebBridgeApi();
    if (!api || !desktopShell) return;
    try {
      const rst = await api.readTrustedStatus();
      if (rst.ok) {
        desktopWebBridgeTrustedRef.current = true;
        setGohamBridgeLinked(true);
        return;
      }
      const snap = await api.getStatus();
      const linked = snap.paired === true;
      desktopWebBridgeTrustedRef.current = linked;
      setGohamBridgeLinked(linked);
    } catch {
      desktopWebBridgeTrustedRef.current = false;
      setGohamBridgeLinked(false);
    }
  }, [desktopShell]);

  React.useEffect(() => {
    if (!desktopShell) {
      desktopWebBridgeTrustedRef.current = false;
      browserSessionFollowThroughRef.current = false;
      setGohamBridgeLinked(false);
      setGohamModalOpen(false);
      setGohamBridgeExplicitlyDisabled(false);
      return;
    }
    void refreshGohamBridgeLinked();
  }, [desktopShell, refreshGohamBridgeLinked]);

  const runGohamTrustedConnect = React.useCallback(async (startingDetail: string | null = null) => {
    const api = getHamDesktopWebBridgeApi();
    if (!api) return;
    setGohamModalPhase("connecting");
    setGohamBridgeExplicitlyDisabled(false);
    setGohamModalDetail(startingDetail);
    try {
      const r = await api.trustedConnect();
      if (r.ok === true) {
        setGohamModalPhase("connected");
        desktopWebBridgeTrustedRef.current = true;
        setGohamBridgeLinked(true);
        setGohamModalDetail(
          r.already_connected ? "Already linked." : "Connected for this session.",
        );
      } else {
        setGohamModalPhase("failed");
        setGohamModalDetail(
          "error" in r && typeof r.error === "string" ? r.error : "trusted_connect_failed",
        );
      }
    } catch (err) {
      setGohamModalPhase("failed");
      setGohamModalDetail(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const openGohamDesktopModal = React.useCallback(async () => {
    setGohamModalOpen(true);
    setGohamModalPhase("checking");
    setGohamModalDetail(null);
    setGohamBridgeExplicitlyDisabled(false);
    const api = getHamDesktopWebBridgeApi();
    if (!api) {
      setGohamModalPhase("failed");
      setGohamModalDetail("Local web bridge API is not available in this build.");
      return;
    }
    try {
      const snap = await api.getStatus();
      if (snap.enabled === false) {
        setGohamModalPhase("blocked");
        const explicitDisable = snap.disabled_reason === "explicit_disabled";
        setGohamBridgeExplicitlyDisabled(explicitDisable);
        setGohamModalDetail(
          explicitDisable
            ? "Local control is disabled. Enable it in Settings."
            : "Local web bridge is disabled on this desktop.",
        );
        return;
      }
      const rst = await api.readTrustedStatus();
      if (rst.ok) {
        setGohamModalPhase("connected");
        desktopWebBridgeTrustedRef.current = true;
        setGohamBridgeLinked(true);
        setGohamModalDetail("Connected for this session.");
        return;
      }
      if (snap.running === false) {
        await runGohamTrustedConnect("Starting local control…");
        return;
      }
      setGohamModalPhase("idle");
    } catch (err) {
      setGohamModalPhase("failed");
      setGohamModalDetail(err instanceof Error ? err.message : "Could not read bridge status.");
    }
  }, [runGohamTrustedConnect]);

  const runGohamRevokeBridge = React.useCallback(async () => {
    const api = getHamDesktopWebBridgeApi();
    if (!api) return;
    try {
      const r = await api.revoke();
      if (r.ok === true) {
        desktopWebBridgeTrustedRef.current = false;
        setGohamBridgeLinked(false);
        setGohamModalPhase("idle");
        setGohamBridgeExplicitlyDisabled(false);
        setGohamModalDetail(null);
      } else {
        setGohamModalPhase("failed");
        setGohamModalDetail(
          "error" in r && typeof r.error === "string" ? r.error : "revoke_failed",
        );
      }
    } catch (err) {
      setGohamModalPhase("failed");
      setGohamModalDetail(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const chatModelIdForApi =
    catalog?.gateway_mode === "openrouter" ||
    (catalog?.gateway_mode === "http" && catalog?.openrouter_user_byok_connected === true)
      ? modelId
      : null;

  const handleComposerModelIdChange = React.useCallback(
    (id: string | null) => {
      setModelId(id);
      const ws = activeWorkspaceIdRef.current?.trim();
      if (!ws) return;
      cancelComposerPrefSaveTimer();
      composerPrefSaveTimerRef.current = setTimeout(() => {
        composerPrefSaveTimerRef.current = null;
        void (async () => {
          try {
            const out = await putChatComposerPreference(ws, { model_id: id });
            if (out.cleared) setModelId(out.model_id ?? null);
          } catch (e) {
            toast.error(e instanceof Error ? e.message : "Could not save model preference.", {
              duration: 8000,
            });
          }
        })();
      }, 450);
    },
    [cancelComposerPrefSaveTimer],
  );

  React.useEffect(() => () => cancelComposerPrefSaveTimer(), [cancelComposerPrefSaveTimer]);

  const refreshContextMeters = React.useCallback(
    async (sessionOverride?: string | null) => {
      const sid = (sessionOverride ?? sessionId)?.trim();
      if (!sid || chatCapabilitiesLoading) return;
      if (!chatCapabilities?.context_meters_enabled) {
        setContextMetersPayload(null);
        return;
      }
      try {
        const mid = chatModelIdForApi ?? modelId;
        const p = await fetchChatContextMeters({
          sessionId: sid,
          modelId: mid,
          projectId,
          workspaceId: activeWorkspaceId,
        });
        setContextMetersPayload(p);
      } catch {
        setContextMetersPayload(null);
      }
    },
    [
      sessionId,
      chatCapabilitiesLoading,
      chatCapabilities?.context_meters_enabled,
      chatModelIdForApi,
      modelId,
      projectId,
      activeWorkspaceId,
    ],
  );

  React.useEffect(() => {
    void refreshContextMeters();
  }, [refreshContextMeters]);
  const runWorkspaceImageGeneration = React.useCallback(
    async (opts: {
      apiPrompt: string;
      transcriptUserLine: string;
      referenceAttachmentId?: string | null;
    }) => {
      const apiPrompt = opts.apiPrompt.trim();
      const transcriptUserLine = (opts.transcriptUserLine.trim() || apiPrompt).trim();
      const referenceAttachmentId =
        typeof opts.referenceAttachmentId === "string" && opts.referenceAttachmentId.trim()
          ? opts.referenceAttachmentId.trim()
          : null;
      if (!apiPrompt) {
        toast.message("Describe the image you want.", { duration: 4000 });
        return;
      }
      if (voiceTranscribing || sending || imageGenInFlight || videoGenInFlight) {
        toast.message("Wait for the current action to finish.", { duration: 4000 });
        return;
      }

      setLoadErr(null);
      setInput("");
      setAttachments((prev) => {
        revokeWorkspaceComposerAttachmentPreviews(prev);
        return [];
      });

      const userRow: HwwMsgRow = {
        id: `hww-user-gimg-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        role: "user",
        content: transcriptUserLine,
        timestamp: timeStr(),
      };
      const assistantPlaceId = `hww-assist-gimg-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      const assistantLoading: HwwMsgRow = {
        id: assistantPlaceId,
        role: "assistant",
        content: "",
        timestamp: timeStr(),
        generatedImageCard: { kind: "loading", promptPreview: apiPrompt.slice(0, 280) },
      };
      setMessages((prev) => [...prev, userRow, assistantLoading]);
      setImageGenInFlight(true);

      try {
        const gen = await postHamGeneratedImage({
          prompt: apiPrompt,
          model_id: chatModelIdForApi,
          ...(referenceAttachmentId ? { reference_attachment_id: referenceAttachmentId } : {}),
        });
        const meta = await fetchHamGeneratedMediaMeta(gen.generated_media_id);
        const blob = await fetchHamGeneratedMediaBlob(gen.generated_media_id);
        const blobUrl = URL.createObjectURL(blob);
        const providerLabel =
          typeof meta.provider === "string" && meta.provider.trim() ? meta.provider.trim() : null;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantPlaceId
              ? {
                  ...m,
                  content: "",
                  generatedImageCard: {
                    kind: "ready",
                    generatedMediaId: meta.generated_media_id,
                    blobUrl,
                    mimeType: meta.mime_type,
                    safeDisplayName: meta.safe_display_name,
                    promptExcerpt: meta.prompt_excerpt ?? "",
                    providerLabel,
                    modelId: meta.model_id,
                    width: meta.width,
                    height: meta.height,
                    generatedFromReference: Boolean(
                      gen.generated_from_reference_image ?? meta.generated_from_reference_image,
                    ),
                  },
                }
              : m,
          ),
        );
      } catch (err) {
        const restricted = err instanceof HamAccessRestrictedError;
        const message = restricted
          ? "Access restricted: this Ham deployment only allows approved sign-ins. Check Clerk or admin."
          : err instanceof Error
            ? err.message
            : "Image generation failed.";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantPlaceId
              ? {
                  ...m,
                  content: "",
                  generatedImageCard: {
                    kind: "error",
                    promptPreview: apiPrompt.slice(0, 280),
                    message,
                  },
                }
              : m,
          ),
        );
        toast.error(message, restricted ? { duration: 12_000 } : { duration: 10_000 });
      } finally {
        setImageGenInFlight(false);
      }
    },
    [chatModelIdForApi, imageGenInFlight, sending, videoGenInFlight, voiceTranscribing],
  );

  const runWorkspaceVideoGeneration = React.useCallback(
    async (opts: { apiPrompt: string; transcriptUserLine: string }) => {
      const apiPrompt = opts.apiPrompt.trim();
      const transcriptUserLine = (opts.transcriptUserLine.trim() || apiPrompt).trim();
      if (!apiPrompt) {
        toast.message("Describe the video you want.", { duration: 4000 });
        return;
      }
      if (voiceTranscribing || sending || imageGenInFlight || videoGenInFlight) {
        toast.message("Wait for the current action to finish.", { duration: 4000 });
        return;
      }

      setLoadErr(null);
      setInput("");
      setAttachments((prev) => {
        revokeWorkspaceComposerAttachmentPreviews(prev);
        return [];
      });

      const userRow: HwwMsgRow = {
        id: `hww-user-gvid-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        role: "user",
        content: transcriptUserLine,
        timestamp: timeStr(),
      };
      const assistantPlaceId = `hww-assist-gvid-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      const assistantLoading: HwwMsgRow = {
        id: assistantPlaceId,
        role: "assistant",
        content: "",
        timestamp: timeStr(),
        generatedVideoCard: {
          kind: "loading",
          promptPreview: apiPrompt.slice(0, 280),
          phase: "queued",
        },
      };
      setMessages((prev) => [...prev, userRow, assistantLoading]);
      setVideoGenInFlight(true);

      try {
        const gen = await postHamGeneratedVideo({
          prompt: apiPrompt,
          model_id: chatModelIdForApi,
        });

        const maxPolls = 90;
        let phase: "queued" | "running" = "queued";
        let terminal:
          | { kind: "succeeded"; generatedMediaId: string }
          | { kind: "failed"; message: string }
          | null = null;
        for (let idx = 0; idx < maxPolls; idx += 1) {
          const status = await fetchHamMediaJobStatus(gen.job_id);
          if (status.status === "queued" || status.status === "running") {
            const nextPhase = status.status;
            if (nextPhase !== phase) {
              phase = nextPhase;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantPlaceId && m.generatedVideoCard?.kind === "loading"
                    ? {
                        ...m,
                        generatedVideoCard: { ...m.generatedVideoCard, phase: nextPhase },
                      }
                    : m,
                ),
              );
            }
            await waitMs(2000);
            continue;
          }
          if (status.status === "succeeded" && typeof status.generated_media_id === "string") {
            terminal = { kind: "succeeded", generatedMediaId: status.generated_media_id };
            break;
          }
          const errText =
            typeof status.error?.message === "string" && status.error.message.trim()
              ? status.error.message.trim()
              : "Video generation failed.";
          terminal = { kind: "failed", message: errText };
          break;
        }

        if (!terminal) {
          terminal = { kind: "failed", message: "Video generation timed out." };
        }

        if (terminal.kind === "failed") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantPlaceId
                ? {
                    ...m,
                    content: "",
                    generatedVideoCard: {
                      kind: "error",
                      promptPreview: apiPrompt.slice(0, 280),
                      message: terminal.message,
                    },
                  }
                : m,
            ),
          );
          toast.error(terminal.message, { duration: 10_000 });
          return;
        }

        const meta = await fetchHamGeneratedMediaMeta(terminal.generatedMediaId);
        const blob = await fetchHamGeneratedMediaBlob(terminal.generatedMediaId);
        const blobUrl = URL.createObjectURL(blob);
        const providerLabel =
          typeof meta.provider === "string" && meta.provider.trim() ? meta.provider.trim() : null;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantPlaceId
              ? {
                  ...m,
                  content: "",
                  generatedVideoCard: {
                    kind: "ready",
                    generatedMediaId: meta.generated_media_id,
                    blobUrl,
                    mimeType: meta.mime_type,
                    safeDisplayName: meta.safe_display_name,
                    promptExcerpt: meta.prompt_excerpt ?? "",
                    providerLabel,
                    modelId: meta.model_id,
                  },
                }
              : m,
          ),
        );
      } catch (err) {
        const restricted = err instanceof HamAccessRestrictedError;
        const message = restricted
          ? "Access restricted: this Ham deployment only allows approved sign-ins. Check Clerk or admin."
          : err instanceof Error
            ? err.message
            : "Video generation failed.";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantPlaceId
              ? {
                  ...m,
                  content: "",
                  generatedVideoCard: {
                    kind: "error",
                    promptPreview: apiPrompt.slice(0, 280),
                    message,
                  },
                }
              : m,
          ),
        );
        toast.error(message, restricted ? { duration: 12_000 } : { duration: 10_000 });
      } finally {
        setVideoGenInFlight(false);
      }
    },
    [chatModelIdForApi, imageGenInFlight, sending, videoGenInFlight, voiceTranscribing],
  );

  const persistLocalDesktopTurn = React.useCallback(
    async (userContent: string, assistantContent: string, sessionHint: string | null) => {
      let sid = sessionHint;
      let createdNew = false;
      try {
        if (!sid) {
          const created = await createChatSession(activeWorkspaceId);
          sid = created.session_id;
          createdNew = true;
          setSessionId(sid);
        }
        if (!sid) return;
        writeWorkspaceLastChatSessionId(activeWorkspaceId, sid);
        if (!embedMode) {
          navigate(
            { pathname: "/workspace/chat", search: `?session=${encodeURIComponent(sid)}` },
            { replace: true },
          );
        }
        const persisted = await appendChatSessionTurns(
          sid,
          [
            { role: "user", content: userContent },
            { role: "assistant", content: assistantContent },
          ],
          activeWorkspaceId,
        );
        setSessionId(persisted.session_id);
        writeWorkspaceLastChatSessionId(activeWorkspaceId, persisted.session_id);
        setMessages((prev) => {
          revokeGeneratedMediaBlobUrlsFromMessages(prev);
          return persisted.messages.map((m, i) => ({
            id: `${persisted.session_id}-persisted-${i}-${m.role}`,
            role: m.role as HwwMsgRow["role"],
            content: m.content,
            timestamp: timeStr(),
          }));
        });
        if (createdNew) {
          setInspectorEvents((prev) =>
            appendInspectorEvent(prev, {
              atIso: new Date().toISOString(),
              kind: "session_assigned",
              status: "ok",
              summary: "Chat session is ready — your link is saved",
              meta: { session_id: persisted.session_id },
            }),
          );
        }
      } catch (err) {
        const reason = err instanceof Error ? err.message : "persist_failed";
        setInspectorEvents((prev) =>
          appendInspectorEvent(prev, {
            atIso: new Date().toISOString(),
            kind: "stream_error",
            status: "warning",
            summary: `Chat persistence warning: ${safeInspectorErrorMessage(reason)}`,
            meta: { code: "local_turn_not_persisted", reason },
          }),
        );
        toast.error(
          `Local browser result is shown, but persistence failed (${reason}). Retry this turn or check API connectivity.`,
          { duration: 10_000 },
        );
      }
    },
    [activeWorkspaceId, embedMode, navigate],
  );

  React.useEffect(() => {
    let c = false;
    setCatalogLoading(true);
    void fetchModelsCatalog()
      .then((r) => {
        if (!c) setCatalog(r);
      })
      .catch(() => {
        if (!c) setCatalog(CLIENT_MODEL_CATALOG_FALLBACK);
      })
      .finally(() => {
        if (!c) setCatalogLoading(false);
      });
    return () => {
      c = true;
    };
  }, []);

  React.useEffect(() => {
    const ws = activeWorkspaceId?.trim();
    if (!ws || !catalog?.items?.length) return;
    let cancelled = false;
    void (async () => {
      try {
        const p = await fetchChatComposerPreference(ws);
        if (cancelled) return;
        let next = p.model_id ?? null;
        const gm = (catalog.gateway_mode || "").toLowerCase();
        if (next == null && gm === "openrouter") {
          next =
            catalog.items.find((i) => i.supports_chat && !i.id.startsWith("cursor:"))?.id ?? null;
        }
        setModelId(next);
      } catch {
        if (cancelled) return;
        const gm = (catalog.gateway_mode || "").toLowerCase();
        if (gm === "openrouter") {
          const first = catalog.items.find((i) => i.supports_chat && !i.id.startsWith("cursor:"));
          setModelId(first?.id ?? null);
        } else {
          setModelId(null);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeWorkspaceId, catalog]);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      setChatCapabilitiesLoading(true);
      try {
        const caps = await fetchChatCapabilities(modelId);
        if (!cancelled) setChatCapabilities(caps);
      } catch {
        if (!cancelled) setChatCapabilities(null);
      } finally {
        if (!cancelled) setChatCapabilitiesLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [modelId]);

  React.useEffect(() => {
    let c = false;
    void (async () => {
      try {
        const ctx = await fetchContextEngine();
        const id = await ensureProjectIdForWorkspaceRoot(ctx.cwd);
        if (!c) {
          setProjectId(id);
          setHamProjectId(id);
        }
      } catch {
        if (!c) {
          setProjectId(null);
          setHamProjectId(null);
        }
      }
    })();
    return () => {
      c = true;
    };
  }, [setHamProjectId]);

  React.useEffect(() => {
    let cancelled = false;
    const missionId = String(missionIdFromQuery || "").trim();
    if (!missionId) {
      setMissionContext(null);
      setMissionError(null);
      setMissionLoading(false);
      return;
    }
    setMissionLoading(true);
    setMissionError(null);
    void (async () => {
      const m = await fetchManagedMissionDetail(missionId);
      if (cancelled) return;
      setMissionLoading(false);
      if (m.mission) {
        setMissionContext(m.mission);
      } else {
        setMissionContext(null);
        setMissionError(m.error ?? "Could not load mission context.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [missionIdFromQuery]);

  const loadFromApi = React.useCallback(
    async (sid: string) => {
      if (sending) {
        return;
      }
      const requestWorkspaceId = activeWorkspaceId;
      const requestStillCurrent = () => activeWorkspaceIdRef.current === requestWorkspaceId;
      setLoadingSession(true);
      setLoadErr(null);
      try {
        const detail = await workspaceSessionAdapter.get(sid, activeWorkspaceId);
        if (!requestStillCurrent()) return;
        const ts = timeStr;
        const prevLoaded = previousLoadedWorkspaceSessionRef.current;
        if (prevLoaded && prevLoaded !== sid) {
          revokeAllChatAttachmentLocalBlobs();
        }
        previousLoadedWorkspaceSessionRef.current = sid;
        setSessionId(sid);
        writeWorkspaceLastChatSessionId(activeWorkspaceId, sid);
        setMessages((prev) => {
          revokeGeneratedMediaBlobUrlsFromMessages(prev);
          return detail.messages.map((m, i) => ({
            id: `${sid}-hww-${i}-${m.role}`,
            role: m.role as HwwMsgRow["role"],
            content: m.content,
            timestamp: ts(),
          }));
        });
        setArtifactRows([]);
        setInspectorEvents((prev) =>
          appendInspectorEvent(prev, {
            atIso: new Date().toISOString(),
            kind: "session_history_loaded",
            status: "info",
            summary: `Loaded session from server (${detail.messages.length} message${detail.messages.length === 1 ? "" : "s"})`,
            meta: {
              session_id: sid,
              message_count: detail.messages.length,
            },
          }),
        );
      } catch (err) {
        if (!requestStillCurrent()) return;
        if (streamTurnSessionRef.current === sid && sending) {
          return;
        }
        const sessionNotFound =
          err instanceof Error && /session not found/i.test(err.message || "");
        setLoadErr(
          "This session could not be loaded. It may have expired, been removed, or belong to a different API revision.",
        );
        if (sessionNotFound) {
          // Only clear durable selection when API confirms session is gone.
          previousLoadedWorkspaceSessionRef.current = null;
          revokeAllChatAttachmentLocalBlobs();
          setSessionId(null);
          writeWorkspaceLastChatSessionId(activeWorkspaceId, null);
          setMessages((prev) => {
            revokeGeneratedMediaBlobUrlsFromMessages(prev);
            return [];
          });
          setInspectorEvents([]);
          setArtifactRows([]);
        }
        toast.error("Could not open this chat session.", {
          id: `hww-session-load-fail-${sid}`,
          duration: 6000,
        });
      } finally {
        if (!requestStillCurrent()) return;
        setLoadingSession(false);
      }
    },
    [activeWorkspaceId, sending, revokeAllChatAttachmentLocalBlobs],
  );

  React.useEffect(() => {
    const prev = previousActiveWorkspaceIdRef.current;
    if (prev === undefined || prev === null) {
      previousActiveWorkspaceIdRef.current = activeWorkspaceId;
      return;
    }
    if (prev === activeWorkspaceId) return;
    previousActiveWorkspaceIdRef.current = activeWorkspaceId;
    suppressSessionQueryUntilNavigationRef.current = true;
    cancelComposerPrefSaveTimer();
    setFailedChatModelIds([]);

    streamTurnSessionRef.current = null;
    lastSessionRestoreScopeRef.current = null;
    previousLoadedWorkspaceSessionRef.current = null;
    revokeAllChatAttachmentLocalBlobs();
    setSessionId(null);
    setLoadErr(null);
    setLoadingSession(false);
    setSending(false);
    setContextMetersPayload(null);
    setExecutionMode(null);
    setMessages((prevRows) => {
      revokeGeneratedMediaBlobUrlsFromMessages(prevRows);
      return [];
    });
    setInspectorEvents([]);
    setArtifactRows([]);
    if (!embedMode && !missionIdFromQuery) {
      navigate({ pathname: "/workspace/chat", search: "" }, { replace: true });
    }
  }, [
    activeWorkspaceId,
    embedMode,
    missionIdFromQuery,
    navigate,
    revokeAllChatAttachmentLocalBlobs,
    cancelComposerPrefSaveTimer,
  ]);

  React.useEffect(() => {
    const sessionParamWhileSwitching = embedMode
      ? null
      : searchParams.get("session")?.trim() || null;
    if (suppressSessionQueryUntilNavigationRef.current && sessionParamWhileSwitching) {
      return;
    }
    if (lastSessionRestoreScopeRef.current === workspaceRestoreScope) return;
    lastSessionRestoreScopeRef.current = workspaceRestoreScope;
    if (sessionId) return;
    // Mission-mode deep links must remain mission-scoped and should not be replaced by saved session URLs.
    if (missionIdFromQuery) return;
    const savedRaw = readWorkspaceLastChatSessionId(activeWorkspaceId);
    if (!savedRaw) return;
    const saved = savedRaw.trim();
    if (!saved) return;
    const fromQuery = embedMode ? null : searchParams.get("session")?.trim() || null;
    if (!embedMode && !fromQuery) {
      navigate(
        { pathname: "/workspace/chat", search: `?session=${encodeURIComponent(saved)}` },
        { replace: true },
      );
    }
    // Deep-link wins: stale last-session ids must not race `?session=` (404 overlays a valid chat).
    if (fromQuery && fromQuery !== saved) {
      return;
    }
    void loadFromApi(saved);
  }, [
    activeWorkspaceId,
    embedMode,
    loadFromApi,
    missionIdFromQuery,
    navigate,
    searchParams,
    sessionId,
    workspaceRestoreScope,
  ]);

  /** Deep link `?session=` (full-page chat only). */
  React.useEffect(() => {
    if (embedMode) return;
    const querySession = searchParams.get("session")?.trim() || null;
    if (suppressSessionQueryUntilNavigationRef.current && querySession) {
      return;
    }
    if (suppressSessionQueryUntilNavigationRef.current && !querySession) {
      suppressSessionQueryUntilNavigationRef.current = false;
    }
    const s = searchParams.get("session");
    if (!s) {
      streamTurnSessionRef.current = null;
      if (sessionId) {
        previousLoadedWorkspaceSessionRef.current = null;
        revokeAllChatAttachmentLocalBlobs();
        setSessionId(null);
        setMessages((prev) => {
          revokeGeneratedMediaBlobUrlsFromMessages(prev);
          return [];
        });
        setInspectorEvents([]);
        setArtifactRows([]);
      }
      return;
    }
    if (s === sessionId) return;
    if (sending && streamTurnSessionRef.current === s) {
      return;
    }
    void loadFromApi(s);
  }, [embedMode, searchParams, sessionId, sending, loadFromApi, revokeAllChatAttachmentLocalBlobs]);

  const startNew = React.useCallback(() => {
    previousLoadedWorkspaceSessionRef.current = null;
    revokeAllChatAttachmentLocalBlobs();
    setSessionId(null);
    writeWorkspaceLastChatSessionId(activeWorkspaceId, null);
    setMessages((prev) => {
      revokeGeneratedMediaBlobUrlsFromMessages(prev);
      return [];
    });
    setInspectorEvents([]);
    setArtifactRows([]);
    setInput("");
    setAttachments((prev) => {
      revokeWorkspaceComposerAttachmentPreviews(prev);
      return [];
    });
    setLoadErr(null);
    if (!embedMode) {
      navigate({ pathname: "/workspace/chat", search: "" }, { replace: true });
    }
    queueMicrotask(() => {
      document.getElementById("hww-chat-composer")?.focus();
    });
  }, [activeWorkspaceId, embedMode, navigate, revokeAllChatAttachmentLocalBlobs]);

  const retryLoadSession = React.useCallback(() => {
    if (embedMode) return;
    const s = searchParams.get("session");
    if (!s?.trim()) return;
    void loadFromApi(s.trim());
  }, [embedMode, searchParams, loadFromApi]);

  React.useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages, sending, imageGenInFlight, videoGenInFlight]);

  const handleAddAttachments = React.useCallback(async (files: File[]) => {
    if (files.length === 0) return;
    const limit = MAX_WORKSPACE_ATTACHMENT_COUNT;
    for (const raw of files) {
      const f = raw;
      if (attachmentsRef.current.some((a) => a.uploadPhase === "uploading")) {
        toast.message("Wait for uploads in progress.", { duration: 4000 });
        return;
      }
      const curLen = attachmentsRef.current.length;
      if (curLen >= limit) {
        toast.error(`Up to ${limit} attachments.`);
        break;
      }
      const staged = await fileToWorkspaceAttachment(f);
      if (staged === null) {
        const isImgGuess =
          /^image\//i.test(f.type || "") || /\.(jpe?g|png|gif|webp)$/i.test(f.name || "");
        const cap = isImgGuess ? MAX_WORKSPACE_IMAGE_BYTES : MAX_WORKSPACE_DOCUMENT_BYTES;
        toast.error(
          `“${f.name || "file"}” is too large (max ${formatAttachmentByteSize(cap)} for ${isImgGuess ? "images" : "documents"}).`,
        );
        continue;
      }
      if (staged.error) {
        setAttachments((prev) => {
          const room = Math.max(0, limit - prev.length);
          return room <= 0 ? prev : [...prev, staged];
        });
        continue;
      }
      const localId = staged.id;
      const uploadingRow: WorkspaceComposerAttachment = {
        ...staged,
        uploadPhase: "uploading",
        pendingSource: f,
      };
      setAttachments((prev) => {
        const room = Math.max(0, limit - prev.length);
        return room <= 0 ? prev : [...prev, uploadingRow];
      });
      const uploadFile = await buildFileForServerUpload(f, staged);
      try {
        const up = await postChatUploadAttachment(uploadFile);
        setAttachments((prev) =>
          prev.map((row) =>
            row.id !== localId
              ? row
              : {
                  ...row,
                  serverId: up.attachment_id,
                  name: up.filename || row.name,
                  size: up.size,
                  mime: up.mime,
                  kind: mapServerAttachmentKind(up.kind),
                  uploadPhase: "done",
                  pendingSource: undefined,
                  error: undefined,
                },
          ),
        );
      } catch (e) {
        const msg =
          e instanceof Error
            ? e.message
            : `Upload failed for "${(uploadFile?.name ?? f.name) || "file"}".`;
        toast.error(msg);
        setAttachments((prev) =>
          prev.map((row) =>
            row.id !== localId
              ? row
              : { ...row, uploadPhase: "failed", error: msg, pendingSource: f },
          ),
        );
      }
    }
  }, []);

  const handleRetryAttachmentUpload = React.useCallback(async (localId: string) => {
    const row = attachmentsRef.current.find((x) => x.id === localId);
    const file = row?.pendingSource;
    if (!row || !file) return;
    if (attachmentsRef.current.some((a) => a.id !== localId && a.uploadPhase === "uploading")) {
      toast.message("Another upload is in progress.", { duration: 4000 });
      return;
    }
    const rebuilt = await fileToWorkspaceAttachment(file);
    if (rebuilt === null) {
      toast.error("File is too large to attach.");
      return;
    }
    if (rebuilt.error) {
      setAttachments((prev) => prev.map((a) => (a.id === localId ? rebuilt : a)));
      return;
    }
    setAttachments((prev) =>
      prev.map((a) =>
        a.id === localId
          ? { ...rebuilt, uploadPhase: "uploading", error: undefined, pendingSource: file }
          : a,
      ),
    );
    const uploadFile = await buildFileForServerUpload(file, rebuilt);
    try {
      const up = await postChatUploadAttachment(uploadFile);
      setAttachments((prev) =>
        prev.map((a) =>
          a.id !== localId
            ? a
            : {
                ...a,
                serverId: up.attachment_id,
                name: up.filename || a.name,
                size: up.size,
                mime: up.mime,
                kind: mapServerAttachmentKind(up.kind),
                uploadPhase: "done",
                pendingSource: undefined,
                error: undefined,
              },
        ),
      );
    } catch (e) {
      const msg =
        e instanceof Error
          ? e.message
          : `Upload failed for "${(uploadFile?.name ?? file.name) || "file"}".`;
      toast.error(msg);
      setAttachments((prev) =>
        prev.map((a) =>
          a.id !== localId ? a : { ...a, uploadPhase: "failed", error: msg, pendingSource: file },
        ),
      );
    }
  }, []);

  const resolveLocalAttachmentPreview = React.useCallback(
    (attachmentServerId: string): string | undefined => {
      return chatAttachmentLocalBlobByServerIdRef.current.get(attachmentServerId);
    },
    [],
  );

  const handleVoiceBlob = React.useCallback(async (blob: Blob) => {
    pushVoiceDebug({
      event: "voice.transcribe.called",
      component: "WorkspaceChatScreen",
      chatScreenInstanceId: chatScreenInstanceId.current,
      blobSize: blob.size,
      blobType: blob.type,
    });
    if (!blob.size) {
      toast.error("No audio captured.");
      return;
    }
    const filename = blob.type.includes("webm")
      ? "dictation.webm"
      : blob.type.includes("mp4") || blob.type.includes("mpeg")
        ? "dictation.m4a"
        : "dictation.webm";
    setVoiceTranscribing(true);
    try {
      const text = (await postChatTranscribe(blob, filename)).trim();
      pushVoiceDebug({
        event: "voice.transcribe.response",
        component: "WorkspaceChatScreen",
        chatScreenInstanceId: chatScreenInstanceId.current,
        ok: true,
        textLength: text.length,
      });
      if (!text) {
        toast.message("No text returned from transcription.");
        return;
      }
      setInput((prev) => (prev.trim() ? `${prev.trim()}\n${text}` : text));
    } catch (err) {
      pushVoiceDebug({
        event: "voice.transcribe.error",
        component: "WorkspaceChatScreen",
        chatScreenInstanceId: chatScreenInstanceId.current,
        message: err instanceof Error ? err.message : "Transcription failed.",
      });
      if (err instanceof HamAccessRestrictedError) {
        toast.error(
          "Access restricted: this Ham deployment only allows approved sign-ins. Check Clerk or admin.",
          { duration: 12_000 },
        );
      } else {
        toast.error(err instanceof Error ? err.message : "Transcription failed.");
      }
    } finally {
      setVoiceTranscribing(false);
    }
  }, []);

  const send = React.useCallback(
    async (outboundUser: string | HamChatUserContentV1 | HamChatUserContentV2) => {
      const isV1 =
        typeof outboundUser === "object" && outboundUser && outboundUser.h === "ham_chat_user_v1";
      const isV2 =
        typeof outboundUser === "object" && outboundUser && outboundUser.h === "ham_chat_user_v2";
      const displayContent =
        isV1 || isV2 ? JSON.stringify(outboundUser) : (outboundUser as string).trim();
      if (!isV1 && !isV2 && !(outboundUser as string).trim()) return;
      if (isV1 && !(outboundUser as HamChatUserContentV1).images?.length) return;
      if (isV2 && !(outboundUser as HamChatUserContentV2).attachments?.length) return;
      if (sending || voiceTranscribing || imageGenInFlight || videoGenInFlight) return;
      const missionModeId = String(missionIdFromQuery || "").trim();
      const outboundPlain = !isV1 && !isV2;
      if (missionModeId && outboundPlain) {
        const plain = String(outboundUser || "").trim();
        if (!plain) return;
        setInput("");
        setAttachments((prev) => {
          revokeWorkspaceComposerAttachmentPreviews(prev);
          return [];
        });
        setLoadErr(null);
        setSending(true);
        const userRow: HwwMsgRow = {
          id: `hww-user-${Date.now()}`,
          role: "user",
          content: plain,
          timestamp: timeStr(),
        };
        const assistantPlaceId = `hww-assist-${Date.now()}`;
        setMessages((prev) => [
          ...prev,
          userRow,
          {
            id: assistantPlaceId,
            role: "assistant",
            content: "",
            timestamp: timeStr(),
          },
        ]);
        const result = await postManagedMissionMessage(missionModeId, plain);
        const assistantMessage = result.error
          ? `Mission follow-up failed: ${result.error}`
          : missionFollowupMessageForReason(result.reasonCode, result.ok);
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantPlaceId ? { ...m, content: assistantMessage } : m)),
        );
        const [mFresh] = await Promise.all([
          fetchManagedMissionDetail(missionModeId),
          refetchMissionFeed(),
        ]);
        setMissionContext(mFresh.mission);
        if (!mFresh.mission) {
          setMissionError(mFresh.error ?? "Could not refresh mission context.");
        }
        setSending(false);
        return;
      }
      if (missionModeId && !outboundPlain) {
        toast.error("Mission follow-up currently supports text-only instructions.");
        return;
      }
      const nlProbeText = outboundPlain
        ? String(outboundUser || "").trim()
        : isV2
          ? String((outboundUser as HamChatUserContentV2).text ?? "").trim()
          : isV1
            ? String((outboundUser as HamChatUserContentV1).text ?? "").trim()
            : "";
      if (!missionModeId && nlProbeText) {
        const trimmedNl = nlProbeText;
        const nlIntent = parseWorkspaceImageGenerationIntent(trimmedNl);
        if (nlIntent) {
          let capsPayload = chatCapabilities;
          if (chatCapabilitiesLoading || capsPayload === null) {
            try {
              capsPayload = await fetchChatCapabilities(modelId);
              setChatCapabilities(capsPayload);
            } catch {
              capsPayload = null;
              setChatCapabilities(null);
            } finally {
              setChatCapabilitiesLoading(false);
            }
          }
          const supportsNl = Boolean(capsPayload?.generation?.supports_image_generation);
          if (!supportsNl) {
            setInput("");
            setAttachments((prev) => {
              revokeWorkspaceComposerAttachmentPreviews(prev);
              return [];
            });
            setLoadErr(null);
            const userNl: HwwMsgRow = {
              id: `hww-user-${Date.now()}`,
              role: "user",
              content: trimmedNl,
              timestamp: timeStr(),
            };
            const assistNl: HwwMsgRow = {
              id: `hww-assist-${Date.now()}`,
              role: "assistant",
              content: "Image generation is not enabled for this workspace yet.",
              timestamp: timeStr(),
            };
            setMessages((prev) => [...prev, userNl, assistNl]);
            return;
          }
          await runWorkspaceImageGeneration({
            apiPrompt: nlIntent,
            transcriptUserLine: trimmedNl,
          });
          return;
        }
      }
      setInput("");
      setAttachments((prev) => {
        revokeWorkspaceComposerAttachmentPreviews(prev);
        return [];
      });
      setLoadErr(null);
      setSending(true);
      streamTurnSessionRef.current = null;
      const requestWorkspaceId = activeWorkspaceId;
      const requestStillCurrent = () => activeWorkspaceIdRef.current === requestWorkspaceId;
      const priorSession = sessionId;
      const userRow: HwwMsgRow = {
        id: `hww-user-${Date.now()}`,
        role: "user",
        content: displayContent,
        timestamp: timeStr(),
      };
      const assistantPlaceId = `hww-assist-${Date.now()}`;
      const assistantRow: HwwMsgRow = {
        id: assistantPlaceId,
        role: "assistant",
        content: "",
        timestamp: timeStr(),
      };
      setMessages((prev) => [...prev, userRow, assistantRow]);
      setInspectorEvents((prev) =>
        appendInspectorEvent(prev, {
          atIso: new Date().toISOString(),
          kind: "user_message_sent",
          status: "info",
          summary: `User message sent (${displayContent.length} character${displayContent.length === 1 ? "" : "s"})`,
          meta: { message_id: userRow.id, char_count: displayContent.length },
        }),
      );
      setInspectorEvents((prev) =>
        appendInspectorEvent(prev, {
          atIso: new Date().toISOString(),
          kind: "assistant_stream_started",
          status: "info",
          summary: "Assistant stream started",
          meta: { message_id: assistantPlaceId },
        }),
      );
      const finalizeLocalBrowserTurn = async (assistantContent: string) => {
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantPlaceId ? { ...m, content: assistantContent } : m)),
        );
        await persistLocalDesktopTurn(displayContent, assistantContent, sessionId);
        setSending(false);
      };
      const plainOutbound = typeof outboundUser === "string" ? (outboundUser as string).trim() : "";
      const browserTaskRequested = outboundPlain && isLikelyBrowserTask(plainOutbound);
      if (desktopShell && browserTaskRequested) {
        const webBridgeApi = getHamDesktopWebBridgeApi();
        if (!webBridgeApi || typeof webBridgeApi.browserIntent !== "function") {
          await finalizeLocalBrowserTurn(
            "Local browser bridge is unavailable in this build. Reconnect GOHAM and retry.",
          );
          setInspectorEvents((prev) =>
            appendInspectorEvent(prev, {
              atIso: new Date().toISOString(),
              kind: "assistant_response_completed",
              status: "warning",
              summary: "Local browser handoff unavailable",
              meta: { reason: "bridge_api_unavailable" },
            }),
          );
          return;
        }

        let trusted = desktopWebBridgeTrustedRef.current;
        try {
          if (!trusted) {
            const rst = await webBridgeApi.readTrustedStatus();
            trusted = rst.ok === true;
            desktopWebBridgeTrustedRef.current = trusted;
            setGohamBridgeLinked(trusted);
          }
        } catch {
          trusted = false;
        }

        if (!trusted) {
          browserSessionFollowThroughRef.current = false;
          await finalizeLocalBrowserTurn("Connect GOHAM first to run browser tasks locally.");
          setInspectorEvents((prev) =>
            appendInspectorEvent(prev, {
              atIso: new Date().toISOString(),
              kind: "assistant_response_completed",
              status: "warning",
              summary: "GOHAM not connected for local browser routing",
              meta: { reason: "trusted_status_missing" },
            }),
          );
          return;
        }

        const localControlApi = getHamDesktopLocalControlApi();
        let activeBrowserSession = false;
        try {
          const st = await localControlApi?.getRealBrowserStatus?.();
          activeBrowserSession = st?.running === true;
        } catch {
          activeBrowserSession = false;
        }

        const providedUrl = extractFirstUrl(plainOutbound);
        const primitiveIntent =
          !providedUrl && activeBrowserSession ? parseLocalCopilotPrimitive(plainOutbound) : null;
        if (primitiveIntent) {
          try {
            if (primitiveIntent.action === "blocked_coordinate") {
              await finalizeLocalBrowserTurn(
                "Coordinate clicks are blocked. Ask me to observe and click a listed candidate.",
              );
              return;
            }
            if (primitiveIntent.action === "observe") {
              const observe = await webBridgeApi.browserIntent({
                intent_id: `desktop-goham-${Date.now()}`,
                action: "observe",
                client_context: { source: "desktop_goham", original_prompt: plainOutbound },
              });
              if (!observe.ok) {
                const reason =
                  typeof observe.reason_code === "string" && observe.reason_code
                    ? observe.reason_code
                    : typeof observe.error === "string"
                      ? observe.error
                      : "observe_failed";
                await finalizeLocalBrowserTurn(localBrowserFailureMessage(reason));
                return;
              }
              const candidates = Array.isArray(
                (observe as Record<string, unknown>).browser_bridge &&
                  typeof (observe as Record<string, unknown>).browser_bridge === "object" &&
                  Array.isArray(
                    ((observe as Record<string, unknown>).browser_bridge as Record<string, unknown>)
                      .click_candidates,
                  )
                  ? ((
                      (observe as Record<string, unknown>).browser_bridge as Record<string, unknown>
                    ).click_candidates as Array<{ id?: string }>)
                  : [],
              )
                ? ((
                    ((observe as Record<string, unknown>).browser_bridge as Record<string, unknown>)
                      .click_candidates as Array<{ id?: string }>
                  ).filter((c) => typeof c?.id === "string") as Array<{ id: string }>)
                : [];
              liveCopilotCandidatesRef.current = candidates;
              browserSessionFollowThroughRef.current = true;
              await finalizeLocalBrowserTurn(
                `Observed locally. Found ${candidates.length} clickable candidates.`,
              );
              return;
            }
            if (primitiveIntent.action === "click_candidate") {
              let candidates = liveCopilotCandidatesRef.current;
              if (!candidates.length) {
                const observe = await webBridgeApi.browserIntent({
                  intent_id: `desktop-goham-${Date.now()}`,
                  action: "observe",
                  client_context: {
                    source: "desktop_goham",
                    original_prompt: "refresh_candidates",
                  },
                });
                if (observe.ok) {
                  const extracted = Array.isArray(
                    (observe as Record<string, unknown>).browser_bridge &&
                      typeof (observe as Record<string, unknown>).browser_bridge === "object" &&
                      Array.isArray(
                        (
                          (observe as Record<string, unknown>).browser_bridge as Record<
                            string,
                            unknown
                          >
                        ).click_candidates,
                      )
                      ? ((
                          (observe as Record<string, unknown>).browser_bridge as Record<
                            string,
                            unknown
                          >
                        ).click_candidates as Array<{ id?: string }>)
                      : [],
                  )
                    ? ((
                        (
                          (observe as Record<string, unknown>).browser_bridge as Record<
                            string,
                            unknown
                          >
                        ).click_candidates as Array<{ id?: string }>
                      ).filter((c) => typeof c?.id === "string") as Array<{ id: string }>)
                    : [];
                  liveCopilotCandidatesRef.current = extracted;
                  candidates = extracted;
                }
              }
              const idx = Math.max(0, primitiveIntent.ordinal - 1);
              const candidateId = candidates[idx]?.id || candidates[0]?.id || "";
              if (!candidateId) {
                await finalizeLocalBrowserTurn(
                  "No safe clickable candidates yet. Ask me to observe first.",
                );
                return;
              }
              const clicked = await webBridgeApi.browserIntent({
                intent_id: `desktop-goham-${Date.now()}`,
                action: "click_candidate",
                candidate_id: candidateId,
                client_context: { source: "desktop_goham", original_prompt: plainOutbound },
              });
              if (!clicked.ok) {
                const reason =
                  typeof clicked.reason_code === "string" && clicked.reason_code
                    ? clicked.reason_code
                    : typeof clicked.error === "string"
                      ? clicked.error
                      : "click_failed";
                await finalizeLocalBrowserTurn(localBrowserFailureMessage(reason));
                return;
              }
              browserSessionFollowThroughRef.current = true;
              await finalizeLocalBrowserTurn("Clicked that locally.");
              return;
            }
            if (primitiveIntent.action === "scroll") {
              const scrolled = await webBridgeApi.browserIntent({
                intent_id: `desktop-goham-${Date.now()}`,
                action: "scroll",
                delta_y: primitiveIntent.delta_y,
                client_context: { source: "desktop_goham", original_prompt: plainOutbound },
              });
              if (!scrolled.ok) {
                const reason =
                  typeof scrolled.reason_code === "string" && scrolled.reason_code
                    ? scrolled.reason_code
                    : typeof scrolled.error === "string"
                      ? scrolled.error
                      : "scroll_failed";
                await finalizeLocalBrowserTurn(localBrowserFailureMessage(reason));
                return;
              }
              browserSessionFollowThroughRef.current = true;
              await finalizeLocalBrowserTurn("Scrolled locally.");
              return;
            }
            if (primitiveIntent.action === "type_into_field") {
              const typed = await webBridgeApi.browserIntent({
                intent_id: `desktop-goham-${Date.now()}`,
                action: "type_into_field",
                selector: primitiveIntent.selector,
                text: primitiveIntent.text,
                clear_first: true,
                client_context: { source: "desktop_goham", original_prompt: plainOutbound },
              });
              if (!typed.ok) {
                const reason =
                  typeof typed.reason_code === "string" && typed.reason_code
                    ? typed.reason_code
                    : typeof typed.error === "string"
                      ? typed.error
                      : "type_failed";
                await finalizeLocalBrowserTurn(localBrowserFailureMessage(reason));
                return;
              }
              browserSessionFollowThroughRef.current = true;
              await finalizeLocalBrowserTurn("Typed into the field locally.");
              return;
            }
            if (primitiveIntent.action === "key_press") {
              const pressed = await webBridgeApi.browserIntent({
                intent_id: `desktop-goham-${Date.now()}`,
                action: "key_press",
                key: primitiveIntent.key,
                client_context: { source: "desktop_goham", original_prompt: plainOutbound },
              });
              if (!pressed.ok) {
                const reason =
                  typeof pressed.reason_code === "string" && pressed.reason_code
                    ? pressed.reason_code
                    : typeof pressed.error === "string"
                      ? pressed.error
                      : "key_press_failed";
                await finalizeLocalBrowserTurn(localBrowserFailureMessage(reason));
                return;
              }
              browserSessionFollowThroughRef.current = true;
              await finalizeLocalBrowserTurn("Pressed that key locally.");
              return;
            }
            if (primitiveIntent.action === "wait") {
              const waited = await webBridgeApi.browserIntent({
                intent_id: `desktop-goham-${Date.now()}`,
                action: "wait",
                wait_ms: primitiveIntent.wait_ms,
                client_context: { source: "desktop_goham", original_prompt: plainOutbound },
              });
              if (!waited.ok) {
                const reason =
                  typeof waited.reason_code === "string" && waited.reason_code
                    ? waited.reason_code
                    : typeof waited.error === "string"
                      ? waited.error
                      : "wait_failed";
                await finalizeLocalBrowserTurn(localBrowserFailureMessage(reason));
                return;
              }
              browserSessionFollowThroughRef.current = true;
              await finalizeLocalBrowserTurn("Paused locally.");
              return;
            }
          } catch (err) {
            const reason = err instanceof Error ? err.message : "browser_intent_failed";
            await finalizeLocalBrowserTurn(localBrowserFailureMessage(reason));
            return;
          }
        } else if (
          !providedUrl &&
          activeBrowserSession &&
          isFollowUpBrowserInstruction(plainOutbound)
        ) {
          browserSessionFollowThroughRef.current = true;
        } else {
          const targetUrl = providedUrl || buildSafeSearchUrl(plainOutbound);
          try {
            const browserIntent = await webBridgeApi.browserIntent({
              intent_id: `desktop-goham-${Date.now()}`,
              action: "navigate_and_capture",
              url: targetUrl,
              client_context: {
                source: "desktop_goham",
                original_prompt: plainOutbound,
              },
            });
            if (browserIntent.ok) {
              browserSessionFollowThroughRef.current = true;
              await finalizeLocalBrowserTurn(
                providedUrl ? "Opening that locally." : "Opening that locally. I found the page.",
              );
              setInspectorEvents((prev) =>
                appendInspectorEvent(prev, {
                  atIso: new Date().toISOString(),
                  kind: "assistant_response_completed",
                  status: "ok",
                  summary: "GOHAM routed browser task to local bridge",
                  meta: { url: targetUrl, browser_task: plainOutbound },
                }),
              );
            } else {
              browserSessionFollowThroughRef.current = false;
              const reason =
                typeof browserIntent.reason_code === "string" && browserIntent.reason_code
                  ? browserIntent.reason_code
                  : typeof browserIntent.error === "string"
                    ? browserIntent.error
                    : "browser_intent_failed";
              await finalizeLocalBrowserTurn(localBrowserFailureMessage(reason));
              setInspectorEvents((prev) =>
                appendInspectorEvent(prev, {
                  atIso: new Date().toISOString(),
                  kind: "assistant_response_completed",
                  status: "warning",
                  summary: `Local browser handoff blocked: ${reason}`,
                  meta: { reason, url: targetUrl },
                }),
              );
            }
            return;
          } catch (err) {
            browserSessionFollowThroughRef.current = false;
            const reason = err instanceof Error ? err.message : "browser_intent_failed";
            await finalizeLocalBrowserTurn(localBrowserFailureMessage(reason));
            setInspectorEvents((prev) =>
              appendInspectorEvent(prev, {
                atIso: new Date().toISOString(),
                kind: "assistant_response_completed",
                status: "error",
                summary: `Local browser handoff failed: ${reason}`,
                meta: { reason },
              }),
            );
            return;
          }
        }
      }

      const streamAuth: HamChatStreamAuth | undefined = await workspaceChatAdapter.getStreamAuth();
      try {
        let execPrefEffective: "auto" | "browser" | "machine" | "chat" = executionModePreference;
        if (
          desktopShell &&
          desktopWebBridgeTrustedRef.current &&
          browserSessionFollowThroughRef.current &&
          outboundPlain &&
          plainOutbound.length > 0 &&
          !/^https?:\/\//i.test(plainOutbound) &&
          execPrefEffective === "auto"
        ) {
          execPrefEffective = "browser";
        }
        const res = await workspaceChatAdapter.stream(
          {
            session_id: sessionId ?? undefined,
            messages: [
              {
                role: "user",
                content:
                  isV1 || isV2
                    ? (outboundUser as HamChatUserContentV1 | HamChatUserContentV2)
                    : (outboundUser as string).trim(),
              },
            ],
            ...(chatModelIdForApi ? { model_id: chatModelIdForApi } : {}),
            ...(projectId ? { project_id: projectId } : {}),
            workbench_mode: "agent",
            worker: "builder",
            max_mode: false,
            execution_mode_preference: execPrefEffective,
            execution_environment: executionEnvironment,
            ...(requestWorkspaceId?.trim() ? { workspace_id: requestWorkspaceId.trim() } : {}),
          },
          {
            onSession: (sid) => {
              if (!requestStillCurrent()) return;
              streamTurnSessionRef.current = sid;
              setSessionId(sid);
              writeWorkspaceLastChatSessionId(requestWorkspaceId, sid);
              if (!embedMode) {
                navigate(
                  { pathname: "/workspace/chat", search: `?session=${encodeURIComponent(sid)}` },
                  { replace: true },
                );
              }
              setInspectorEvents((prev) => {
                const patched = patchInspectorEventsSessionId(prev, sid);
                if (sid === priorSession) return patched;
                return appendInspectorEvent(patched, {
                  atIso: new Date().toISOString(),
                  kind: "session_assigned",
                  status: "ok",
                  summary: "Chat session is ready — your link is saved",
                  meta: { session_id: sid },
                });
              });
            },
            onDelta: (delta) => {
              if (!requestStillCurrent()) return;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantPlaceId ? { ...m, content: m.content + delta } : m,
                ),
              );
            },
          },
          streamAuth,
        );
        if (!requestStillCurrent()) return;
        setSessionId(res.session_id);
        writeWorkspaceLastChatSessionId(requestWorkspaceId, res.session_id);
        setExecutionMode(res.execution_mode ?? null);
        browserSessionFollowThroughRef.current = res.execution_mode?.selected_mode === "browser";
        const normalizedMessages = res.messages.some((m) => m.role === "user")
          ? res.messages
          : [{ role: "user" as const, content: displayContent }, ...res.messages];
        setMessages((prev) => {
          revokeGeneratedMediaBlobUrlsFromMessages(prev);
          const next = normalizedMessages.map((m, i) => ({
            id: `${res.session_id}-done-${i}-${m.role}`,
            role: m.role,
            content: m.content,
            timestamp: timeStr(),
          }));
          return next;
        });
        const assistantLast = [...res.messages].reverse().find((m) => m.role === "assistant");
        const assistantChars = assistantLast?.content?.length ?? 0;
        setInspectorEvents((prev) =>
          appendInspectorEvent(prev, {
            atIso: new Date().toISOString(),
            kind: "assistant_response_completed",
            status: res.gateway_error ? "warning" : "ok",
            summary: res.gateway_error
              ? `Assistant response completed — gateway warning: ${res.gateway_error.code}`
              : `Assistant response completed (${assistantChars} character${assistantChars === 1 ? "" : "s"})`,
            meta: {
              session_id: res.session_id,
              message_count: res.messages.length,
              assistant_char_count: assistantChars,
              ...(res.gateway_error?.code ? { gateway_code: res.gateway_error.code } : {}),
            },
          }),
        );
        if (res.gateway_error?.code === "OPENROUTER_MODEL_REJECTED") {
          const mid = chatModelIdForApi;
          if (mid) {
            setFailedChatModelIds((prev) => (prev.includes(mid) ? prev : [...prev, mid]));
          }
          toast.error(
            "OpenRouter rejected the selected model. Switch back to Hermes Agent / Default or choose a recommended model.",
            {
              action: {
                label: "Use Hermes default",
                onClick: () => {
                  cancelComposerPrefSaveTimer();
                  setModelId(null);
                  const w = activeWorkspaceIdRef.current?.trim();
                  if (w) {
                    void putChatComposerPreference(w, { model_id: null }).then((out) => {
                      if (out.cleared) setModelId(out.model_id ?? null);
                    });
                  }
                },
              },
              duration: 12_000,
            },
          );
        }
        applyHamUiActions(res.actions ?? [], {
          navigate,
          setIsControlPanelOpen: () => {},
          isControlPanelOpen: false,
        });
        setArtifactRows((prev) =>
          mergeArtifactRowsAfterTurn(
            prev,
            new Date().toISOString(),
            res.actions,
            res.operator_result ?? null,
            res.execution_mode ?? null,
          ),
        );
      } catch (err) {
        if (!requestStillCurrent()) return;
        const safeMsg = safeInspectorErrorMessage(
          err instanceof HamAccessRestrictedError
            ? "Access restricted (email or domain not allowed for this deployment)."
            : err instanceof Error
              ? err.message
              : "Request failed",
        );
        const sidForRecovery =
          (err instanceof HamChatStreamIncompleteError ? err.streamSessionId : null) ??
          streamTurnSessionRef.current ??
          sessionId ??
          null;

        let recoveredFromServer = false;
        if (!(err instanceof HamAccessRestrictedError) && sidForRecovery) {
          try {
            const detail = await workspaceSessionAdapter.get(sidForRecovery, requestWorkspaceId);
            if (!requestStillCurrent()) return;
            if (detail.messages.length > 0) {
              recoveredFromServer = true;
              setSessionId(detail.session_id);
              writeWorkspaceLastChatSessionId(requestWorkspaceId, detail.session_id);
              setMessages((prev) => {
                revokeGeneratedMediaBlobUrlsFromMessages(prev);
                return detail.messages.map((m, i) => ({
                  id: `${detail.session_id}-recovered-${i}-${m.role}`,
                  role: m.role,
                  content: m.content,
                  timestamp: timeStr(),
                }));
              });
            }
          } catch {
            /* session refetch is best-effort */
          }
        }

        if (recoveredFromServer) {
          setInspectorEvents((prev) =>
            appendInspectorEvent(prev, {
              atIso: new Date().toISOString(),
              kind: "stream_recovered",
              status: "warning",
              summary: "Stream interrupted — restored messages from the server",
              meta: sidForRecovery ? { session_id: sidForRecovery } : undefined,
            }),
          );
          toast.message(
            "Connection interrupted. Chat was restored from the server. Ask me to continue if the last reply cuts off.",
            { duration: 10_000 },
          );
        } else {
          setInspectorEvents((prev) =>
            appendInspectorEvent(prev, {
              atIso: new Date().toISOString(),
              kind: "stream_error",
              status: "error",
              summary: `Stream error: ${safeMsg}`,
              meta: {
                code:
                  err instanceof HamAccessRestrictedError
                    ? "HAM_EMAIL_RESTRICTION"
                    : "stream_error",
              },
            }),
          );
          if (err instanceof HamAccessRestrictedError) {
            const msg =
              "Access restricted: this Ham deployment only allows approved sign-ins. Check Clerk or admin.";
            setLoadErr(msg);
            toast.error(msg, { duration: 12_000 });
          } else if (
            err instanceof HamChatStreamIncompleteError ||
            (err instanceof Error && err.message === "Chat stream ended without a done event")
          ) {
            toast.error(
              "Connection interrupted. Partial reply is kept below — ask me to continue if it cuts off.",
              { duration: 10_000 },
            );
          } else {
            const msg = err instanceof Error ? err.message : "Request failed";
            toast.error(msg, { duration: 8_000 });
          }
          setMessages((prev) => {
            const assist = prev.find((m) => m.id === assistantPlaceId);
            if (assist && assist.content.trim().length > 0) {
              return prev;
            }
            return prev.filter((m) => m.id !== assistantPlaceId);
          });
        }
      } finally {
        streamTurnSessionRef.current = null;
        if (requestStillCurrent()) {
          setSending(false);
          void refreshContextMeters();
        }
      }
    },
    [
      embedMode,
      sending,
      voiceTranscribing,
      imageGenInFlight,
      videoGenInFlight,
      sessionId,
      activeWorkspaceId,
      chatModelIdForApi,
      projectId,
      missionIdFromQuery,
      refetchMissionFeed,
      navigate,
      executionModePreference,
      executionEnvironment,
      desktopShell,
      persistLocalDesktopTurn,
      chatCapabilities,
      chatCapabilitiesLoading,
      modelId,
      runWorkspaceImageGeneration,
      refreshContextMeters,
      cancelComposerPrefSaveTimer,
    ],
  );

  const handleComposerGenerateImage = React.useCallback(() => {
    const trimmed = input.trim();
    const usable = attachments.filter(
      (a) => !a.error && a.uploadPhase !== "failed" && a.uploadPhase !== "uploading",
    );
    const firstImageId = usable.find((a) => a.kind === "image" && a.serverId)?.serverId ?? null;

    if (!trimmed) {
      if (firstImageId) {
        toast.message("Describe how to change the image.", { duration: 4000 });
      } else {
        toast.message("Describe the image you want.", { duration: 4000 });
      }
      return;
    }

    if (firstImageId && !chatCapabilities?.generation?.supports_image_to_image) {
      toast.message("Image editing is not enabled yet for this workspace.", { duration: 5000 });
      return;
    }

    void runWorkspaceImageGeneration({
      apiPrompt: trimmed,
      transcriptUserLine: trimmed,
      referenceAttachmentId:
        firstImageId && chatCapabilities?.generation?.supports_image_to_image ? firstImageId : null,
    });
  }, [
    attachments,
    chatCapabilities?.generation?.supports_image_to_image,
    input,
    runWorkspaceImageGeneration,
  ]);

  const handleComposerGenerateVideo = React.useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed) {
      toast.message("Describe the video you want.", { duration: 4000 });
      return;
    }
    if (attachments.some((a) => a.uploadPhase === "uploading")) {
      toast.message("Wait for uploads to finish.", { duration: 3800 });
      return;
    }
    if (attachments.length > 0) {
      toast.message("Generate video uses text prompt only in this MVP.", { duration: 4500 });
      return;
    }
    void runWorkspaceVideoGeneration({
      apiPrompt: trimmed,
      transcriptUserLine: trimmed,
    });
  }, [attachments, input, runWorkspaceVideoGeneration]);

  const composerGenerateImage = React.useMemo((): ComposerGenerateImageState => {
    const uploadsPending = attachments.some((a) => a.uploadPhase === "uploading");
    const supportsGen = Boolean(chatCapabilities?.generation?.supports_image_generation);
    const supportsI2i = Boolean(chatCapabilities?.generation?.supports_image_to_image);
    const activeProvider = String(chatCapabilities?.generation?.active_media_provider || "")
      .trim()
      .toLowerCase();
    const comfyProfile = String(chatCapabilities?.generation?.comfy_worker_profile || "").trim();
    const providerLabel = activeProvider
      ? activeProvider === "comfyui"
        ? comfyProfile
          ? `ComfyUI (${comfyProfile})`
          : "ComfyUI"
        : activeProvider
      : "unknown provider";
    const hasReadyImage = attachments.some(
      (a) =>
        !a.error &&
        a.uploadPhase !== "failed" &&
        a.uploadPhase !== "uploading" &&
        a.kind === "image" &&
        Boolean(a.serverId),
    );
    let subtitle = `Create from your composer prompt (${providerLabel})`;
    if (chatCapabilitiesLoading) subtitle = "Checking workspace capabilities…";
    else if (!supportsGen) subtitle = `Image generation unavailable (${providerLabel})`;
    else if (hasReadyImage && !supportsI2i) subtitle = "Image editing is not enabled yet.";
    else if (uploadsPending) subtitle = "Finish uploads before generating";

    const refBlocked = hasReadyImage && supportsGen && !supportsI2i;

    const disabled =
      uploadsPending ||
      catalogLoading ||
      chatCapabilitiesLoading ||
      !supportsGen ||
      refBlocked ||
      sending ||
      voiceTranscribing ||
      imageGenInFlight ||
      videoGenInFlight;

    return {
      onGenerate: handleComposerGenerateImage,
      busy: imageGenInFlight,
      disabled,
      subtitle,
    };
  }, [
    attachments,
    catalogLoading,
    chatCapabilities?.generation?.active_media_provider,
    chatCapabilities?.generation?.comfy_worker_profile,
    chatCapabilities?.generation?.supports_image_generation,
    chatCapabilities?.generation?.supports_image_to_image,
    chatCapabilitiesLoading,
    handleComposerGenerateImage,
    imageGenInFlight,
    sending,
    voiceTranscribing,
    videoGenInFlight,
  ]);

  const composerGenerateVideo = React.useMemo((): ComposerGenerateVideoState => {
    const uploadsPending = attachments.some((a) => a.uploadPhase === "uploading");
    const supportsVideo = Boolean(
      chatCapabilities?.generation?.supports_video_generation ||
      chatCapabilities?.generation?.supports_text_to_video,
    );
    const provider = String(
      chatCapabilities?.generation?.media_generation_provider ||
        chatCapabilities?.generation?.active_media_provider ||
        "",
    ).trim();
    let subtitle = "Create short clip";
    if (chatCapabilitiesLoading) subtitle = "Checking workspace capabilities…";
    else if (!supportsVideo) subtitle = "Video generation unavailable";
    else if (uploadsPending) subtitle = "Finish uploads before generating";
    else if (provider) subtitle = `Create short clip (${provider})`;

    const disabled =
      uploadsPending ||
      catalogLoading ||
      chatCapabilitiesLoading ||
      !supportsVideo ||
      sending ||
      voiceTranscribing ||
      imageGenInFlight ||
      videoGenInFlight;

    return {
      onGenerate: handleComposerGenerateVideo,
      busy: videoGenInFlight,
      disabled,
      subtitle,
    };
  }, [
    attachments,
    catalogLoading,
    chatCapabilities?.generation?.supports_text_to_video,
    chatCapabilities?.generation?.supports_video_generation,
    chatCapabilities?.generation?.active_media_provider,
    chatCapabilities?.generation?.media_generation_provider,
    chatCapabilitiesLoading,
    handleComposerGenerateVideo,
    imageGenInFlight,
    sending,
    videoGenInFlight,
    voiceTranscribing,
  ]);

  const onFormSubmit = () => {
    void (async () => {
      const trimmed = input.trim();
      const usable = attachments.filter(
        (a) => !a.error && a.uploadPhase !== "failed" && a.uploadPhase !== "uploading",
      );
      if (voiceTranscribing || imageGenInFlight || videoGenInFlight) return;
      if (attachments.some((a) => a.uploadPhase === "uploading")) {
        toast.message("Wait for uploads to finish.", { duration: 3800 });
        return;
      }
      if (attachments.length > 0 && usable.length === 0) {
        toast.error(
          "Every attachment failed or is invalid — remove errors or retry uploads, then try again.",
        );
        return;
      }
      if (usable.length > 0) {
        if (usable.every((a) => a.serverId)) {
          const missionEarly = String(missionIdFromQuery || "").trim();
          const imageRef =
            trimmed.length > 0 ? usable.find((a) => a.kind === "image" && a.serverId) : undefined;
          const creative =
            trimmed.length > 0 && imageRef?.serverId
              ? parseWorkspaceCreativeImageIntent(trimmed, { hasImageAttachment: true })
              : null;

          if (!missionEarly && creative?.kind === "image_to_image" && imageRef?.serverId) {
            if (voiceTranscribing || imageGenInFlight || videoGenInFlight) return;
            if (chatCapabilitiesLoading) {
              toast.message("Checking workspace capabilities…", { duration: 3800 });
              return;
            }
            if (!chatCapabilities?.generation?.supports_image_generation) {
              setInput("");
              setAttachments((prev) => {
                revokeWorkspaceComposerAttachmentPreviews(prev);
                return [];
              });
              setLoadErr(null);
              const userNl: HwwMsgRow = {
                id: `hww-user-${Date.now()}`,
                role: "user",
                content: trimmed,
                timestamp: timeStr(),
              };
              const assistNl: HwwMsgRow = {
                id: `hww-assist-${Date.now()}`,
                role: "assistant",
                content: "Image generation is not enabled for this workspace yet.",
                timestamp: timeStr(),
              };
              setMessages((prev) => [...prev, userNl, assistNl]);
              return;
            }
            if (!chatCapabilities?.generation?.supports_image_to_image) {
              setInput("");
              setAttachments((prev) => {
                revokeWorkspaceComposerAttachmentPreviews(prev);
                return [];
              });
              setLoadErr(null);
              const userNl: HwwMsgRow = {
                id: `hww-user-${Date.now()}`,
                role: "user",
                content: trimmed,
                timestamp: timeStr(),
              };
              const assistNl: HwwMsgRow = {
                id: `hww-assist-${Date.now()}`,
                role: "assistant",
                content:
                  "Image editing from a reference image is not enabled yet for this workspace.",
                timestamp: timeStr(),
              };
              setMessages((prev) => [...prev, userNl, assistNl]);
              return;
            }
            await runWorkspaceImageGeneration({
              apiPrompt: creative.prompt,
              transcriptUserLine: trimmed,
              referenceAttachmentId: imageRef.serverId,
            });
            return;
          }

          await stashImageBlobsForServerIdsBeforeSend(usable);
          const payload = buildHamChatUserPayloadV2(
            trimmed,
            usable.map((a) => ({
              id: a.serverId!,
              name: a.name,
              mime:
                a.mime ??
                (a.kind === "image"
                  ? "image/png"
                  : a.kind === "video"
                    ? "video/mp4"
                    : "text/plain"),
              kind: a.kind,
            })),
          );
          void send(payload);
          return;
        }
        const payload = buildHamChatUserPayloadV1(
          trimmed,
          usable
            .filter((a) => a.kind === "image" && a.payload.startsWith("data:"))
            .map((a) => {
              const m = /^data:(image\/(?:png|jpe?g|webp));base64,/i.exec(a.payload.trim());
              const raw = (m ? m[1] : "image/jpeg").toLowerCase();
              const mime = raw === "image/jpg" ? "image/jpeg" : raw;
              return { name: a.name, mime, dataUrl: a.payload, size: a.size };
            }),
        );
        if (payload.images.length === 0) {
          toast.error("Re-add attachments (upload may have been interrupted).");
          return;
        }
        void send(payload);
        return;
      }
      if (!trimmed) return;

      if (!String(missionIdFromQuery || "").trim()) {
        const nlIntentImage = parseWorkspaceImageGenerationIntent(trimmed);
        if (nlIntentImage) {
          if (voiceTranscribing || imageGenInFlight || videoGenInFlight) return;

          let capsPayload = chatCapabilities;
          if (chatCapabilitiesLoading || capsPayload === null) {
            try {
              capsPayload = await fetchChatCapabilities(modelId);
              setChatCapabilities(capsPayload);
            } catch {
              capsPayload = null;
              setChatCapabilities(null);
            } finally {
              setChatCapabilitiesLoading(false);
            }
          }

          if (capsPayload?.generation?.supports_image_generation) {
            await runWorkspaceImageGeneration({
              apiPrompt: nlIntentImage,
              transcriptUserLine: trimmed,
            });
            return;
          }
          // Workspace has no image capability (or caps fetch failed): fall through to video/chat routing.
        }
      }

      const supportsComposerVideo =
        Boolean(
          chatCapabilities?.generation?.supports_video_generation ||
          chatCapabilities?.generation?.supports_text_to_video,
        ) && String(missionIdFromQuery || "").trim().length === 0;

      if (
        supportsComposerVideo &&
        !chatCapabilitiesLoading &&
        !catalogLoading &&
        shouldEnqueueVideoOnComposerSend({
          trimmed,
          supportsVideo: supportsComposerVideo,
          gatewayMode: catalog?.gateway_mode ?? null,
        })
      ) {
        void runWorkspaceVideoGeneration({
          apiPrompt: trimmed,
          transcriptUserLine: trimmed,
        });
        return;
      }

      void send(trimmed);
    })();
  };

  const handleExportPdf = React.useCallback(() => {
    if (!sessionId) return;
    void (async () => {
      setPdfExporting(true);
      try {
        await downloadChatSessionPdf(sessionId, activeWorkspaceId);
        toast.success("Chat exported to PDF");
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "PDF export failed");
      } finally {
        setPdfExporting(false);
      }
    })();
  }, [activeWorkspaceId, sessionId]);

  const handleRemoveGeneratedImage = React.useCallback((assistantMessageId: string) => {
    setMessages((prev) => {
      const next: HwwMsgRow[] = [];
      for (const m of prev) {
        if (m.id !== assistantMessageId) {
          next.push(m);
          continue;
        }
        if (!m.generatedImageCard) {
          next.push(m);
          continue;
        }
        revokeGeneratedMediaBlobUrlsFromMessages([m]);
        const textOnly = (m.content || "").trim();
        if (textOnly) {
          next.push({ ...m, generatedImageCard: undefined });
        }
      }
      return next;
    });
  }, []);

  const handleRemoveGeneratedVideo = React.useCallback((assistantMessageId: string) => {
    setMessages((prev) => {
      const next: HwwMsgRow[] = [];
      for (const m of prev) {
        if (m.id !== assistantMessageId) {
          next.push(m);
          continue;
        }
        if (!m.generatedVideoCard) {
          next.push(m);
          continue;
        }
        revokeGeneratedMediaBlobUrlsFromMessages([m]);
        const textOnly = (m.content || "").trim();
        if (textOnly) {
          next.push({ ...m, generatedVideoCard: undefined });
        }
      }
      return next;
    });
  }, []);

  const hasTranscript = messages.length > 0;
  const showEmpty = !loadingSession && !hasTranscript && !loadErr;
  const sessionLoadFailed = Boolean(loadErr && !hasTranscript && !loadingSession);
  const staleSessionParam = embedMode ? null : searchParams.get("session");
  const missionModeActive = Boolean(missionIdFromQuery);
  const missionTitle = missionContext?.title || missionContext?.task_summary || "Mission";
  const missionBannerLifecycle = missionFeed?.lifecycle ?? missionContext?.mission_lifecycle;
  const missionBannerCheckpoint =
    missionFeed?.latest_checkpoint ??
    missionContext?.latest_checkpoint ??
    missionContext?.cursor_status_last_observed ??
    "waiting";
  const headerTitle = sessionLoadFailed
    ? "Session unavailable"
    : missionModeActive
      ? "Mission chat"
      : !sessionId
        ? "New session"
        : "Chat";
  const last = messages[messages.length - 1];
  const isStreaming =
    sending &&
    last?.role === "assistant" &&
    !(last?.content || "").trim() &&
    !last.generatedImageCard &&
    !last.generatedVideoCard;

  let pdfExportBlockedReason: ComposerExportPdfState["blockedReason"] = "none";
  if (sessionLoadFailed) pdfExportBlockedReason = "session_error";
  else if (!sessionId) pdfExportBlockedReason = "no_session";
  else if (!hasTranscript) pdfExportBlockedReason = "no_transcript";
  else if (isStreaming) pdfExportBlockedReason = "streaming";

  const headerSubtitle = missionModeActive
    ? "Mission-scoped follow-up mode. Your messages are routed to this mission."
    : workspaceChatSubtitle({
        sessionLoadFailed,
        staleSessionParam,
        sessionId,
        messages,
      });

  const missionAgentActivityContent: React.ReactNode = missionModeActive ? (
    missionLoading ? (
      <div className="p-3">
        <p className="text-[12px] leading-relaxed text-white/60">Loading mission context…</p>
      </div>
    ) : missionError ? (
      <div className="p-3">
        <p className="text-[12px] leading-relaxed text-amber-200/80">{missionError}</p>
      </div>
    ) : missionContext ? (
      <div className="divide-y divide-white/[0.06]">
        <div className="space-y-2 px-3 py-2.5">
          <div className="flex flex-wrap items-start gap-2">
            <span
              className={cn(
                "shrink-0 rounded px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide",
                missionContext.provider === "cursor"
                  ? "border border-emerald-400/35 bg-emerald-500/10 text-emerald-200/90"
                  : "border border-white/[0.08] bg-white/[0.06] text-white/55",
              )}
            >
              {missionContext.provider === "cursor" ? "Cursor" : "Cloud Agent"}
            </span>
            <p className="min-w-0 flex-1 text-[12px] leading-snug text-white/[0.88]">
              {formatMissionStatusTitleForDisplay(missionTitle)}
              <span className="text-white/35"> · </span>
              {missionBannerLifecycle}
              <span className="text-white/35"> · </span>
              {missionBannerCheckpoint}
            </p>
          </div>
          <p className="text-[10px] leading-relaxed text-white/40">
            {missionContext.repository_observed || "—"} @ {missionContext.ref_observed || "default"}{" "}
            · mission{" "}
            <span className="font-mono text-white/45" title={missionContext.mission_registry_id}>
              {shortId(missionContext.mission_registry_id)}
            </span>
            <span className="text-white/35"> · agent </span>
            <span className="font-mono text-white/45">
              {shortId(missionContext.cursor_agent_id)}
            </span>
            {isBcCursorAgentId(missionContext.cursor_agent_id) ? (
              <a
                href={cursorCloudAgentWebHref(String(missionContext.cursor_agent_id).trim())}
                target="_blank"
                rel="noopener noreferrer"
                title="Open this Cloud Agent in Cursor"
                className="ml-2 inline-flex items-center gap-1 text-[10px] font-medium text-[#ffb27a]/90 underline-offset-2 hover:underline"
              >
                Open in Cursor
                <ExternalLink className="h-3 w-3 opacity-70" aria-hidden />
              </a>
            ) : null}
          </p>
          <p className="text-[10px] leading-relaxed text-white/40">
            {MANAGED_MISSION_CHAT_OWNERSHIP_HINT}
          </p>
          {missionFeedBanner.phase !== "idle" && missionFeedBanner.label ? (
            <p className="text-[10px] leading-relaxed text-emerald-200/85">
              {missionFeedBanner.label}
            </p>
          ) : missionFeed?.provider_projection?.mode === "rest_projection" ? (
            <p className="text-[10px] leading-relaxed text-white/45">
              Mission feed: REST refresh only (not a live provider stream).
            </p>
          ) : null}
        </div>
        <div className="space-y-1.5 px-3 py-2.5">
          {(missionFeed?.events || []).length > 0 ? (
            <ChatMissionFeedTranscript
              items={displayedMissionFeedTranscript}
              anchorRef={missionFeedScrollAnchorRef}
            />
          ) : missionFeedInitialLoading ? (
            <p className="text-[10px] leading-relaxed text-white/40">Loading mission feed…</p>
          ) : (
            <p className="text-[10px] leading-relaxed text-white/40">
              Waiting for mission feed updates…
            </p>
          )}
        </div>
      </div>
    ) : (
      <div className="p-3">
        <p className="text-[12px] leading-relaxed text-white/60">
          Mission context is not available.
        </p>
      </div>
    )
  ) : null;

  const onChatSplitResizePointerDown = React.useCallback(
    (e: React.PointerEvent<HTMLButtonElement>) => {
      if (!isDesktopSplitLayout) return;
      e.preventDefault();
      splitDragRef.current = {
        startX: e.clientX,
        startW: cmdPanelWidthPxRef.current,
      };
      setSplitResizePointerDown(true);
    },
    [isDesktopSplitLayout],
  );

  return (
    <div
      ref={chatSplitRowRef}
      data-testid="hww-chat-split-row"
      className="flex min-h-0 w-full min-w-0 flex-1 flex-col md:flex-row"
    >
      <div
        data-testid="hww-command-panel"
        className={cn(
          "flex min-h-0 max-w-full min-w-0 flex-1 flex-col overflow-x-hidden md:flex-none",
          "w-full border-b border-white/[0.06] md:border-b-0 md:border-r md:border-white/[0.08] md:shrink-0 md:overflow-x-hidden",
        )}
        style={
          isDesktopSplitLayout
            ? {
                width: cmdPanelWidthPx,
                minWidth: HWW_CHAT_CMD_PANEL_MIN_PX,
                maxWidth: HWW_CHAT_CMD_PANEL_MAX_PX,
              }
            : undefined
        }
      >
        <header
          data-testid="hww-chat-header-compact"
          data-hww-chat-header-compact="true"
          data-hww-chat-header-mission-active={missionModeActive ? "true" : "false"}
          data-hww-chat-header-session-load-failed={sessionLoadFailed ? "true" : "false"}
          className="hww-chat-header flex min-h-[52px] shrink-0 items-center justify-between gap-3 border-b border-white/[0.06] bg-[#040d14]/80 px-4 py-2.5 backdrop-blur-sm md:px-8"
        >
          <div className="flex min-w-0 flex-1 items-center gap-2.5">
            <img
              src={hamWorkspaceLogoUrl()}
              alt=""
              className="h-8 w-8 shrink-0 object-contain opacity-95"
              width={32}
              height={32}
            />
            <span className="sr-only">
              {headerTitle}. {headerSubtitle}
            </span>
            {missionModeActive ? (
              <span className="max-w-[min(100%,12rem)] truncate text-[11px] font-medium text-emerald-200/95">
                Mission chat
              </span>
            ) : sessionLoadFailed ? (
              <span className="text-[11px] font-semibold tracking-tight text-amber-100/95">
                Session unavailable
              </span>
            ) : null}
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              type="button"
              data-testid="hww-chat-inspector-tab"
              data-active={inspectorOpen ? "true" : "false"}
              onClick={() => {
                setInspectorOpen((o) => !o);
              }}
              className={cn(
                "inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1.5 text-[11px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-emerald-400/30",
                inspectorOpen
                  ? "bg-emerald-500/15 text-[#e8eef8] shadow-[inset_0_0_0_1px_rgba(16,185,129,0.25),0_0_16px_rgba(16,185,129,0.08)]"
                  : "text-white/45 hover:bg-white/[0.06] hover:text-white/75",
              )}
              aria-pressed={inspectorOpen}
              title={inspectorOpen ? "Close inspector" : "Open inspector"}
            >
              {inspectorOpen ? (
                <PanelRightClose className="h-3.5 w-3.5 opacity-90" strokeWidth={1.5} />
              ) : (
                <PanelRight className="h-3.5 w-3.5 opacity-90" strokeWidth={1.5} />
              )}
              <span className="hidden sm:inline select-none">Inspector</span>
            </button>
          </div>
        </header>
        <div className="grid min-h-0 min-w-0 max-w-full flex-1 grid-rows-[minmax(0,1fr)_auto] overflow-x-hidden">
          <div
            ref={listWrapRef}
            className="hww-chat-command-feed hww-scroll flex min-h-0 min-w-0 max-w-full flex-col overflow-x-hidden overflow-y-auto px-3 md:px-6"
          >
            {loadingSession ? (
              <div className="flex flex-1 items-center justify-center py-12 text-sm text-white/40">
                Loading…
              </div>
            ) : sessionLoadFailed ? (
              <div className="flex flex-1 flex-col items-center justify-center px-4 py-10">
                <div
                  className="w-full max-w-md rounded-xl border border-amber-500/25 bg-[#040d14]/90 px-5 py-5 text-left shadow-lg"
                  role="alert"
                >
                  <h2 className="text-[14px] font-semibold text-amber-100/95">
                    Could not open this session
                  </h2>
                  <p className="mt-2 text-[13px] leading-relaxed text-white/70">{loadErr}</p>
                  {staleSessionParam ? (
                    <p className="mt-2 text-[11px] text-white/45">
                      If you need help, support can use the link in your browser’s address bar.
                    </p>
                  ) : null}
                  <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
                    <Button
                      type="button"
                      size="sm"
                      className="bg-[#7dd3fc] text-[#040d14] hover:bg-[#a5e9ff]"
                      onClick={startNew}
                    >
                      Start new session
                    </Button>
                    <Button type="button" size="sm" variant="secondary" onClick={startNew}>
                      Back to recent sessions
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="border-white/15 bg-transparent text-white/85 hover:bg-white/[0.06]"
                      onClick={retryLoadSession}
                    >
                      Retry
                    </Button>
                  </div>
                  <p className="mt-4 text-[11px] leading-relaxed text-white/35">
                    The sidebar stays available — pick another session or start fresh. If this link
                    is old, the API may have been redeployed; chat history on Cloud Run defaults to
                    ephemeral storage unless configured otherwise.
                  </p>
                </div>
              </div>
            ) : showEmpty ? (
              <WorkspaceChatEmptyState />
            ) : (
              <>
                <WorkspaceChatMessageList
                  messages={messages}
                  isStreaming={isStreaming}
                  resolveLocalAttachmentPreview={resolveLocalAttachmentPreview}
                  onRemoveGeneratedImage={handleRemoveGeneratedImage}
                  onRemoveGeneratedVideo={handleRemoveGeneratedVideo}
                />
                <div ref={endRef} className="h-2 shrink-0" />
              </>
            )}
          </div>
          <div className="flex w-full max-w-full min-w-0 shrink-0 flex-col overflow-x-hidden">
            <WorkspaceChatComposer
              quickSuggestions={WORKSPACE_CHAT_SUGGESTIONS}
              onQuickSuggestion={(prompt) => void send(prompt)}
              quickTipsResetSignal={sessionId}
              value={input}
              onChange={setInput}
              onSubmit={onFormSubmit}
              disabled={catalogLoading}
              sending={sending || imageGenInFlight || videoGenInFlight}
              voiceTranscribing={voiceTranscribing}
              onVoiceBlob={handleVoiceBlob}
              attachments={attachments}
              onAddAttachments={handleAddAttachments}
              onRemoveAttachment={(id) => {
                setAttachments((p) => {
                  const dying = p.find((a) => a.id === id);
                  if (dying) revokeWorkspaceComposerAttachmentPreviews([dying]);
                  return p.filter((a) => a.id !== id);
                });
              }}
              onPasteFiles={handleAddAttachments}
              onRetryAttachmentUpload={(lid) => void handleRetryAttachmentUpload(lid)}
              catalog={catalog}
              modelId={modelId}
              onModelIdChange={handleComposerModelIdChange}
              failedChatModelIds={new Set(failedChatModelIds)}
              sttDictationEnabled={sttDictationEnabled}
              sttUnavailableReason={sttUnavailableReason}
              sttMode={sttMode}
              onSttModeChange={handleSttModeChange}
              gohamDesktopChip={
                desktopShell && getHamDesktopWebBridgeApi()
                  ? {
                      linked: gohamBridgeLinked,
                      busy:
                        gohamModalOpen &&
                        (gohamModalPhase === "checking" || gohamModalPhase === "connecting"),
                      onOpenModal: () => void openGohamDesktopModal(),
                    }
                  : null
              }
              chatCapabilities={chatCapabilities}
              contextMetersEnabled={chatCapabilities?.context_meters_enabled === true}
              contextMetersPayload={contextMetersPayload}
              generateImage={composerGenerateImage}
              generateVideo={composerGenerateVideo}
              exportPdf={{
                onExport: handleExportPdf,
                busy: pdfExporting,
                blockedReason: pdfExportBlockedReason,
              }}
            />
          </div>
        </div>
      </div>
      {isDesktopSplitLayout ? (
        <button
          type="button"
          data-testid="hww-chat-split-resizer"
          aria-label="Resize command and workbench panels"
          title="Drag to resize panels"
          className={cn(
            "group flex h-full min-h-0 shrink-0 cursor-col-resize border-0 bg-transparent p-0",
            "w-[var(--hww-split-resizer)] touch-none select-none flex-col items-stretch justify-stretch",
            "border-l border-r border-transparent hover:border-white/[0.06]",
          )}
          style={{ "--hww-split-resizer": `${HWW_CHAT_SPLIT_RESIZER_PX}px` } as React.CSSProperties}
          onPointerDown={onChatSplitResizePointerDown}
        >
          <span
            className={cn(
              "pointer-events-none my-2 w-px flex-1 self-center rounded-full bg-white/[0.14]",
              "transition-colors group-hover:bg-white/[0.28] group-active:bg-emerald-400/45",
            )}
            aria-hidden
          />
        </button>
      ) : null}
      {desktopShell && gohamModalOpen ? (
        <>
          <button
            type="button"
            className="fixed inset-0 z-[35] cursor-default bg-black/65 backdrop-blur-[1px]"
            aria-label="Close GOHAM local web bridge dialog"
            onClick={() => {
              setGohamModalOpen(false);
              setGohamModalPhase("idle");
              setGohamBridgeExplicitlyDisabled(false);
              setGohamModalDetail(null);
            }}
          />
          <div
            className="fixed left-1/2 top-[8%] z-[36] max-h-[min(78vh,32rem)] w-[min(100%,26rem)] -translate-x-1/2 overflow-y-auto rounded-xl border border-emerald-500/22 bg-[#040d14]/[0.98] p-5 text-[13px] text-white/88 shadow-[0_20px_50px_rgba(0,0,0,0.55)]"
            role="dialog"
            aria-modal="true"
            aria-labelledby="ham-goham-desktop-heading"
          >
            <div className="border-b border-white/[0.08] pb-3">
              <h2
                id="ham-goham-desktop-heading"
                className="text-[15px] font-semibold text-white/[0.95]"
              >
                GOHAM · Local web bridge
              </h2>
              <p className="mt-1 text-[11px] leading-snug text-white/50">
                One-click trusted connect uses the packaged desktop preload path — no manual pairing
                code here.
              </p>
            </div>
            <div className="mt-3 space-y-3">
              {gohamModalPhase === "checking" || gohamModalPhase === "connecting" ? (
                <p className="flex items-center gap-2 text-[12px] text-emerald-100/85">
                  <Loader2 className="h-4 w-4 shrink-0 animate-spin opacity-95" aria-hidden />
                  {gohamModalPhase === "checking"
                    ? "Checking status…"
                    : "Connecting trusted session…"}
                </p>
              ) : null}
              {gohamModalPhase === "blocked" ? (
                <div className="space-y-2 rounded-md border border-amber-500/25 bg-amber-950/35 px-2.5 py-2 text-[12px] text-amber-100/95">
                  <p>
                    <span className="font-medium text-amber-200/95">Blocked.</span>{" "}
                    {gohamModalDetail || "Bridge disabled or policy blocked this desktop."}
                  </p>
                  {gohamBridgeExplicitlyDisabled ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="border-amber-400/35 bg-transparent text-amber-100 hover:bg-amber-400/10"
                      onClick={() => {
                        setGohamModalOpen(false);
                        setGohamModalPhase("idle");
                        setGohamBridgeExplicitlyDisabled(false);
                        setGohamModalDetail(null);
                        navigate("/workspace/settings?section=agent");
                      }}
                    >
                      Open Settings
                    </Button>
                  ) : null}
                </div>
              ) : null}
              {gohamModalPhase === "failed" ? (
                <p className="rounded-md border border-red-500/28 bg-red-950/35 px-2.5 py-2 text-[12px] text-red-100/95">
                  <span className="font-medium text-red-200/95">Failed.</span> {gohamModalDetail}
                </p>
              ) : null}
              {gohamModalPhase === "connected" ? (
                <p className="rounded-md border border-emerald-500/25 bg-emerald-950/35 px-2.5 py-2 text-[12px] text-emerald-100/95">
                  <span className="font-medium text-emerald-200/95">Connected.</span>{" "}
                  {gohamModalDetail || "Trusted local-control session active."}
                </p>
              ) : null}
              {gohamModalPhase === "idle" && gohamModalDetail ? (
                <p className="text-[12px] text-white/60">{gohamModalDetail}</p>
              ) : null}
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              {gohamModalPhase === "idle" ||
              gohamModalPhase === "failed" ||
              gohamModalPhase === "connected" ? (
                <Button
                  type="button"
                  size="sm"
                  className="bg-[#34d399] font-medium text-[#041014] hover:bg-[#5eead4]"
                  onClick={() => void runGohamTrustedConnect()}
                >
                  {gohamModalPhase === "connected" ? "Renew trusted session" : "Connect trusted"}
                </Button>
              ) : null}
              {gohamModalPhase === "connected" ? (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="border-white/15 bg-transparent text-white/85 hover:bg-white/[0.06]"
                  onClick={() => void runGohamRevokeBridge()}
                >
                  Revoke
                </Button>
              ) : null}
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="text-white/65 hover:bg-white/[0.06]"
                onClick={() => {
                  setGohamModalOpen(false);
                  setGohamModalPhase("idle");
                  setGohamBridgeExplicitlyDisabled(false);
                  setGohamModalDetail(null);
                }}
              >
                Close
              </Button>
            </div>
          </div>
        </>
      ) : null}
      {inspectorOpen ? (
        <>
          <button
            type="button"
            className="fixed inset-0 z-20 bg-black/50 md:hidden"
            onClick={() => {
              setInspectorOpen(false);
            }}
            aria-label="Close inspector"
          />
          <div
            className={cn(
              "z-30 flex max-h-full overflow-hidden shadow-2xl",
              "fixed right-0 top-0 h-full md:static md:z-auto md:h-full md:min-h-0 md:shadow-none",
              "w-full md:min-w-[420px] md:flex-1 md:max-w-none",
            )}
          >
            <WorkspaceChatInspectorPanel
              sessionId={sessionId}
              events={inspectorEvents}
              artifactRows={artifactRows}
              executionMode={executionMode}
              agentActivity={missionAgentActivityContent}
              fillColumn
              onClose={() => {
                setInspectorOpen(false);
              }}
            />
          </div>
        </>
      ) : (
        <div
          data-testid="hww-workbench-panel-slot"
          className={cn(
            "relative z-0 flex min-h-0 w-full min-w-0 flex-col overflow-x-hidden",
            "min-h-[260px] max-h-[48vh] md:max-h-none md:h-full md:min-h-0 md:min-w-[420px] md:flex-1",
          )}
        >
          <WorkspaceWorkbench projectId={projectId} />
        </div>
      )}
    </div>
  );
}
