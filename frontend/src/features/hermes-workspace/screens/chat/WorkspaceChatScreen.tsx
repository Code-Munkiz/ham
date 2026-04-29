/**
 * Workspace-native chat: upstream Hermes `ChatScreen` visual/IA pattern, HAM `/api/chat/stream` only.
 * Hermes Workspace chat only (no legacy workbench chrome).
 */

import * as React from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Loader2, PanelRight, PanelRightClose } from "lucide-react";
import { toast } from "sonner";
import {
  ensureProjectIdForWorkspaceRoot,
  fetchContextEngine,
  fetchModelsCatalog,
  HamAccessRestrictedError,
  postChatTranscribe,
  postChatUploadAttachment,
  type HamChatExecutionMode,
} from "@/lib/ham/api";
import { CLIENT_MODEL_CATALOG_FALLBACK } from "@/lib/ham/modelCatalogFallback";
import type { ModelCatalogPayload } from "@/lib/ham/types";
import { applyHamUiActions } from "@/lib/ham/applyUiActions";
import type { HamChatStreamAuth } from "@/lib/ham/api";
import type { HamChatUserContentV1, HamChatUserContentV2 } from "@/lib/ham/chatUserContent";
import {
  buildHamChatUserPayloadV1,
  buildHamChatUserPayloadV2,
  userTranscriptPreview,
} from "@/lib/ham/chatUserContent";
import { workspaceChatAdapter, workspaceSessionAdapter } from "../../workspaceAdapters";
import { useVoiceWorkspaceSettingsOptional } from "../../voice/VoiceWorkspaceSettingsContext";
import { WorkspaceChatEmptyState } from "./WorkspaceChatEmptyState";
import { WorkspaceChatMessageList, type HwwMsgRow } from "./WorkspaceChatMessageList";
import { WorkspaceChatComposer } from "./WorkspaceChatComposer";
import { WorkspaceChatInspectorPanel } from "./WorkspaceChatInspectorPanel";
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
  MAX_WORKSPACE_ATTACHMENT_BYTES,
  MAX_WORKSPACE_ATTACHMENT_COUNT,
  type WorkspaceComposerAttachment,
} from "./composerAttachmentHelpers";
import { Button } from "@/components/ui/button";
import { hamWorkspaceLogoUrl } from "@/lib/ham/publicAssets";
import { cn } from "@/lib/utils";
import { isHamDesktopShell } from "@/lib/ham/desktopConfig";
import { getHamDesktopLocalControlApi, getHamDesktopWebBridgeApi } from "@/lib/ham/desktopBundleBridge";

const VOICE_DEBUG_FLAG = "ham.voiceDebug";

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
    /\b(click|scroll|what do you see|what do you notice|read this page)\b/,
  ];
  return patterns.some((p) => p.test(t));
}

function isFollowUpBrowserInstruction(text: string): boolean {
  const t = text.trim().toLowerCase();
  if (!t) return false;
  return /\b(click|scroll|type|select|open that|what do you see|what does this page|read the page)\b/.test(t);
}

function buildSafeSearchUrl(text: string): string {
  const q = text
    .replace(/\b(open|browser|search|look up|lookup|find|for me|please)\b/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
  return `https://duckduckgo.com/?q=${encodeURIComponent(q || text.trim())}`;
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
    default:
      return `Local browser handoff failed (${reason || "unknown_error"}).`;
  }
}

export type WorkspaceChatScreenProps = {
  /** In-shell drawer: keep session off the URL; do not navigate on new session. */
  embedMode?: boolean;
};

export function WorkspaceChatScreen(props: WorkspaceChatScreenProps = {}) {
  const { embedMode = false } = props;
  const navigate = useNavigate();
  const desktopShell = isHamDesktopShell();
  const executionEnvironment: "desktop" | "web" = desktopShell ? "desktop" : "web";
  const chatScreenInstanceId = React.useRef(`chat-screen-${Math.random().toString(36).slice(2, 9)}`);
  const [searchParams] = useSearchParams();
  const [messages, setMessages] = React.useState<HwwMsgRow[]>([]);
  const [sessionId, setSessionId] = React.useState<string | null>(null);
  const [input, setInput] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const [loadErr, setLoadErr] = React.useState<string | null>(null);
  const [loadingSession, setLoadingSession] = React.useState(false);
  const [catalog, setCatalog] = React.useState<ModelCatalogPayload | null>(null);
  const [catalogLoading, setCatalogLoading] = React.useState(true);
  const [modelId, setModelId] = React.useState<string | null>(null);
  const executionModePreference: "auto" | "browser" | "machine" | "chat" = "auto";
  const [executionMode, setExecutionMode] = React.useState<HamChatExecutionMode | null>(null);
  const [projectId, setProjectId] = React.useState<string | null>(null);
  const [attachments, setAttachments] = React.useState<WorkspaceComposerAttachment[]>([]);
  const [voiceTranscribing, setVoiceTranscribing] = React.useState(false);
  const [inspectorOpen, setInspectorOpen] = React.useState(false);
  const [inspectorEvents, setInspectorEvents] = React.useState<WorkspaceInspectorEvent[]>([]);
  const [artifactRows, setArtifactRows] = React.useState<ChatInspectorArtifactRow[]>([]);
  /** Desktop GOHAM web bridge: trusted session is main-process only; this tracks UI + follow-up routing. */
  const desktopWebBridgeTrustedRef = React.useRef(false);
  /** After a turn used browser execution, follow-up plain text can stay on current screen (desktop + trusted bridge). */
  const browserSessionFollowThroughRef = React.useRef(false);
  const [gohamModalOpen, setGohamModalOpen] = React.useState(false);
  const [gohamBridgeLinked, setGohamBridgeLinked] = React.useState(false);
  const [gohamModalPhase, setGohamModalPhase] = React.useState<
    "idle" | "checking" | "connecting" | "connected" | "blocked" | "failed"
  >("idle");
  const [gohamModalDetail, setGohamModalDetail] = React.useState<string | null>(null);
  const [gohamBridgeExplicitlyDisabled, setGohamBridgeExplicitlyDisabled] = React.useState(false);
  /** When set, deep-link effect must not call `loadFromApi` for this session while the stream turn is active. */
  const streamTurnSessionRef = React.useRef<string | null>(null);
  const endRef = React.useRef<HTMLDivElement | null>(null);
  const listWrapRef = React.useRef<HTMLDivElement | null>(null);

  const voiceWs = useVoiceWorkspaceSettingsOptional();
  const sttEnabledBySetting = voiceWs?.payload?.settings.stt.enabled ?? true;
  const sttMode = voiceWs?.payload?.settings.stt.mode ?? "record";
  const sttRuntimeAvailable = voiceWs?.payload?.capabilities.stt.available ?? true;
  const sttDictationEnabled =
    sttEnabledBySetting && (sttMode !== "record" || sttRuntimeAvailable);
  const sttUnavailableReason =
    !sttEnabledBySetting
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
        setGohamModalDetail(r.already_connected ? "Already linked." : "Connected for this session.");
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

  const chatModelIdForApi = catalog?.gateway_mode === "openrouter" ? modelId : null;

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
    if (!catalog?.items?.length) return;
    const first = catalog.items.find((i) => i.supports_chat);
    setModelId((prev) => prev ?? (first?.id ?? null));
  }, [catalog]);

  React.useEffect(() => {
    let c = false;
    void (async () => {
      try {
        const ctx = await fetchContextEngine();
        const id = await ensureProjectIdForWorkspaceRoot(ctx.cwd);
        if (!c) setProjectId(id);
      } catch {
        if (!c) setProjectId(null);
      }
    })();
    return () => {
      c = true;
    };
  }, []);

  const loadFromApi = React.useCallback(
    async (sid: string) => {
      if (streamTurnSessionRef.current === sid && sending) {
        return;
      }
      setLoadingSession(true);
      setLoadErr(null);
      try {
        const detail = await workspaceSessionAdapter.get(sid);
        const ts = timeStr;
        setSessionId(sid);
        setMessages(
          detail.messages.map((m, i) => ({
            id: `${sid}-hww-${i}-${m.role}`,
            role: m.role as HwwMsgRow["role"],
            content: m.content,
            timestamp: ts(),
          })),
        );
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
      } catch {
        if (streamTurnSessionRef.current === sid && sending) {
          return;
        }
        setLoadErr(
          "This session could not be loaded. It may have expired, been removed, or belong to a different API revision.",
        );
        setSessionId(null);
        setMessages([]);
        setInspectorEvents([]);
        setArtifactRows([]);
        toast.error("Could not open this chat session.", { id: `hww-session-load-fail-${sid}`, duration: 6000 });
      } finally {
        setLoadingSession(false);
      }
    },
    [sending],
  );

  /** Deep link `?session=` (full-page chat only). */
  React.useEffect(() => {
    if (embedMode) return;
    const s = searchParams.get("session");
    if (!s) {
      streamTurnSessionRef.current = null;
      if (sessionId) {
        setSessionId(null);
        setMessages([]);
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
  }, [embedMode, searchParams, sessionId, sending, loadFromApi]);

  const startNew = React.useCallback(() => {
    setSessionId(null);
    setMessages([]);
    setInspectorEvents([]);
    setArtifactRows([]);
    setInput("");
    setAttachments([]);
    setLoadErr(null);
    if (!embedMode) {
      navigate({ pathname: "/workspace/chat", search: "" }, { replace: true });
    }
    queueMicrotask(() => {
      document.getElementById("hww-chat-composer")?.focus();
    });
  }, [embedMode, navigate]);

  const retryLoadSession = React.useCallback(() => {
    if (embedMode) return;
    const s = searchParams.get("session");
    if (!s?.trim()) return;
    void loadFromApi(s.trim());
  }, [embedMode, searchParams, loadFromApi]);

  React.useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages, sending]);

  const handleAddAttachments = React.useCallback(async (files: File[]) => {
    if (files.length === 0) return;
    const next: WorkspaceComposerAttachment[] = [];
    for (const f of files) {
      try {
        const a = await fileToWorkspaceAttachment(f);
        if (a == null) {
          toast.error(
            `“${f.name || "file"}” is too large (max ${formatAttachmentByteSize(MAX_WORKSPACE_ATTACHMENT_BYTES)} per file, after compression for images).`,
          );
          continue;
        }
        if (a.error) {
          next.push(a);
          continue;
        }
        const uploadFile = await buildFileForServerUpload(f, a);
        const up = await postChatUploadAttachment(uploadFile);
        next.push({
          ...a,
          serverId: up.attachment_id,
          name: up.filename || a.name,
          size: up.size,
          mime: up.mime,
          kind: up.kind === "file" ? "file" : "image",
        });
      } catch (e) {
        toast.error(
          e instanceof Error ? e.message : `Upload failed for "${f.name || "file"}".`,
        );
      }
    }
    if (next.length === 0) return;
    setAttachments((prev) => {
      const room = Math.max(0, MAX_WORKSPACE_ATTACHMENT_COUNT - prev.length);
      const add = next.slice(0, room);
      if (next.length > room) {
        toast.error(`Up to ${MAX_WORKSPACE_ATTACHMENT_COUNT} attachments.`);
      }
      return [...prev, ...add];
    });
  }, []);

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
      const isV1 = typeof outboundUser === "object" && outboundUser && outboundUser.h === "ham_chat_user_v1";
      const isV2 = typeof outboundUser === "object" && outboundUser && outboundUser.h === "ham_chat_user_v2";
      const displayContent = isV1 || isV2
        ? JSON.stringify(outboundUser)
        : (outboundUser as string).trim();
      if (!isV1 && !isV2 && !(outboundUser as string).trim()) return;
      if (isV1 && !(outboundUser as HamChatUserContentV1).images?.length) return;
      if (isV2 && !(outboundUser as HamChatUserContentV2).attachments?.length) return;
      if (sending || voiceTranscribing) return;
      setInput("");
      setAttachments([]);
      setLoadErr(null);
      setSending(true);
      streamTurnSessionRef.current = null;
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
      const plainOutbound =
        typeof outboundUser === "string" ? (outboundUser as string).trim() : "";
      const outboundPlain = !isV1 && !isV2;
      const browserTaskRequested = outboundPlain && isLikelyBrowserTask(plainOutbound);
      if (desktopShell && browserTaskRequested) {
        const webBridgeApi = getHamDesktopWebBridgeApi();
        if (!webBridgeApi || typeof webBridgeApi.browserIntent !== "function") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantPlaceId
                ? { ...m, content: "Local browser bridge is unavailable in this build. Reconnect GOHAM and retry." }
                : m,
            ),
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
          setSending(false);
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
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantPlaceId
                ? { ...m, content: "Connect GOHAM first to run browser tasks locally." }
                : m,
            ),
          );
          setInspectorEvents((prev) =>
            appendInspectorEvent(prev, {
              atIso: new Date().toISOString(),
              kind: "assistant_response_completed",
              status: "warning",
              summary: "GOHAM not connected for local browser routing",
              meta: { reason: "trusted_status_missing" },
            }),
          );
          setSending(false);
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
        const followUpInstruction =
          !providedUrl && activeBrowserSession && isFollowUpBrowserInstruction(plainOutbound);
        if (followUpInstruction) {
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
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantPlaceId
                    ? {
                        ...m,
                        content: providedUrl
                          ? "Opening that locally."
                          : "Opening that locally. I found the page.",
                      }
                    : m,
                ),
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
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantPlaceId
                    ? { ...m, content: localBrowserFailureMessage(reason) }
                    : m,
                ),
              );
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
            setSending(false);
            return;
          } catch (err) {
            browserSessionFollowThroughRef.current = false;
            const reason = err instanceof Error ? err.message : "browser_intent_failed";
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantPlaceId
                  ? { ...m, content: localBrowserFailureMessage(reason) }
                  : m,
              ),
            );
            setInspectorEvents((prev) =>
              appendInspectorEvent(prev, {
                atIso: new Date().toISOString(),
                kind: "assistant_response_completed",
                status: "error",
                summary: `Local browser handoff failed: ${reason}`,
                meta: { reason },
              }),
            );
            setSending(false);
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
                content: isV1 || isV2 ? (outboundUser as HamChatUserContentV1 | HamChatUserContentV2) : (outboundUser as string).trim(),
              },
            ],
            ...(chatModelIdForApi ? { model_id: chatModelIdForApi } : {}),
            ...(projectId ? { project_id: projectId } : {}),
            workbench_mode: "agent",
            worker: "builder",
            max_mode: false,
            execution_mode_preference: execPrefEffective,
            execution_environment: executionEnvironment,
          },
          {
            onSession: (sid) => {
              streamTurnSessionRef.current = sid;
              setSessionId(sid);
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
              setMessages((prev) =>
                prev.map((m) => (m.id === assistantPlaceId ? { ...m, content: m.content + delta } : m)),
              );
            },
          },
          streamAuth,
        );
        setSessionId(res.session_id);
        setExecutionMode(res.execution_mode ?? null);
        browserSessionFollowThroughRef.current =
          res.execution_mode?.selected_mode === "browser";
        setMessages(
          res.messages.map((m, i) => ({
            id: `${res.session_id}-done-${i}-${m.role}`,
            role: m.role,
            content: m.content,
            timestamp: timeStr(),
          })),
        );
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
              ...(res.gateway_error?.code
                ? { gateway_code: res.gateway_error.code }
                : {}),
            },
          }),
        );
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
        const safeMsg = safeInspectorErrorMessage(
          err instanceof HamAccessRestrictedError
            ? "Access restricted (email or domain not allowed for this deployment)."
            : err instanceof Error
              ? err.message
              : "Request failed",
        );
        setInspectorEvents((prev) =>
          appendInspectorEvent(prev, {
            atIso: new Date().toISOString(),
            kind: "stream_error",
            status: "error",
            summary: `Stream error: ${safeMsg}`,
            meta: {
              code: err instanceof HamAccessRestrictedError ? "HAM_EMAIL_RESTRICTION" : "stream_error",
            },
          }),
        );
        if (err instanceof HamAccessRestrictedError) {
          const msg =
            "Access restricted: this Ham deployment only allows approved sign-ins. Check Clerk or admin.";
          setLoadErr(msg);
          toast.error(msg, { duration: 12_000 });
        } else if (
          err instanceof Error &&
          err.message === "Chat stream ended without a done event"
        ) {
          const msg = "Response was interrupted — partial message may be saved.";
          toast.error(msg, { duration: 8_000 });
        } else {
          const msg = err instanceof Error ? err.message : "Request failed";
          toast.error(msg, { duration: 8_000 });
        }
        setMessages((prev) => prev.filter((m) => m.id !== assistantPlaceId));
      } finally {
        streamTurnSessionRef.current = null;
        setSending(false);
      }
    },
    [
      embedMode,
      sending,
      voiceTranscribing,
      sessionId,
      chatModelIdForApi,
      projectId,
      navigate,
      executionModePreference,
      executionEnvironment,
      desktopShell,
    ],
  );

  const onFormSubmit = () => {
    const trimmed = input.trim();
    const usable = attachments.filter((a) => !a.error);
    if (voiceTranscribing) return;
    if (attachments.length > 0 && usable.length === 0) {
      toast.error("Every attachment failed. Remove them or add PNG, JPEG, or WebP under 500 KB, then try again.");
      return;
    }
    if (usable.length > 0) {
      if (usable.every((a) => a.serverId)) {
        const payload = buildHamChatUserPayloadV2(
          trimmed,
          usable.map((a) => ({
            id: a.serverId!,
            name: a.name,
            mime: a.mime ?? (a.kind === "file" ? "text/plain" : "image/png"),
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

    void send(trimmed);
  };

  const hasTranscript = messages.length > 0;
  const showEmpty = !loadingSession && !hasTranscript && !loadErr;
  const sessionLoadFailed = Boolean(loadErr && !hasTranscript && !loadingSession);
  const staleSessionParam = embedMode ? null : searchParams.get("session");
  const headerTitle = sessionLoadFailed
    ? "Session unavailable"
    : !sessionId
      ? "New session"
      : "Chat";
  const last = messages[messages.length - 1];
  const isStreaming =
    sending && last?.role === "assistant" && !(last?.content || "").trim();

  const headerSubtitle = workspaceChatSubtitle({
    sessionLoadFailed,
    staleSessionParam,
    sessionId,
    messages,
  });

  return (
    <div className="flex min-h-0 w-full min-w-0 flex-1 flex-col md:flex-row">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="hww-chat-header flex shrink-0 items-start justify-between gap-3 border-b border-white/[0.06] bg-[#040d14]/80 px-4 py-3 backdrop-blur-sm md:px-8">
          <div className="flex min-w-0 items-start gap-2.5">
            <img
              src={hamWorkspaceLogoUrl()}
              alt=""
              className="mt-0.5 h-8 w-8 shrink-0 object-contain opacity-95"
              width={32}
              height={32}
            />
            <div className="min-w-0">
              <h1 className="text-[15px] font-semibold tracking-tight text-white/[0.95]">{headerTitle}</h1>
              <p className="mt-0.5 truncate text-[11px] leading-snug text-white/50">{headerSubtitle}</p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              type="button"
              onClick={() => {
                setInspectorOpen((o) => !o);
              }}
              className={cn(
                "inline-flex h-9 items-center gap-1 rounded-lg border px-2.5 text-[11px] font-medium transition",
                inspectorOpen
                  ? "border-[#c45c12]/50 bg-white/[0.08] text-[#ffb27a]"
                  : "border-white/[0.1] bg-white/[0.06] text-white/80 hover:bg-white/[0.09] hover:text-white",
              )}
              aria-pressed={inspectorOpen}
              title={inspectorOpen ? "Close inspector" : "Open inspector"}
            >
              {inspectorOpen ? (
                <PanelRightClose className="h-3.5 w-3.5" strokeWidth={1.5} />
              ) : (
                <PanelRight className="h-3.5 w-3.5" strokeWidth={1.5} />
              )}
              <span className="hidden sm:inline">Inspector</span>
            </button>
          </div>
        </header>
        <div
          ref={listWrapRef}
          className="hww-scroll flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto"
        >
          {loadingSession ? (
            <div className="flex flex-1 items-center justify-center py-12 text-sm text-white/40">Loading…</div>
          ) : sessionLoadFailed ? (
            <div className="flex flex-1 flex-col items-center justify-center px-4 py-10">
              <div
                className="w-full max-w-md rounded-xl border border-amber-500/25 bg-[#040d14]/90 px-5 py-5 text-left shadow-lg"
                role="alert"
              >
                <h2 className="text-[14px] font-semibold text-amber-100/95">Could not open this session</h2>
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
                  The sidebar stays available — pick another session or start fresh. If this link is old, the API may
                  have been redeployed; chat history on Cloud Run defaults to ephemeral storage unless configured
                  otherwise.
                </p>
              </div>
            </div>
          ) : showEmpty ? (
            <WorkspaceChatEmptyState onSuggestionClick={(prompt) => void send(prompt)} />
          ) : (
            <>
              <WorkspaceChatMessageList messages={messages} isStreaming={isStreaming} />
              <div ref={endRef} className="h-2 shrink-0" />
            </>
          )}
        </div>
        <div className="flex w-full justify-center px-3 md:px-6">
          <WorkspaceChatComposer
            value={input}
            onChange={setInput}
            onSubmit={onFormSubmit}
            disabled={catalogLoading}
            sending={sending}
            voiceTranscribing={voiceTranscribing}
            onVoiceBlob={handleVoiceBlob}
            attachments={attachments}
            onAddAttachments={handleAddAttachments}
            onRemoveAttachment={(id) => {
              setAttachments((p) => p.filter((a) => a.id !== id));
            }}
            catalog={catalog}
            modelId={modelId}
            onModelIdChange={setModelId}
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
          />
        </div>
      </div>
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
              <h2 id="ham-goham-desktop-heading" className="text-[15px] font-semibold text-white/[0.95]">
                GOHAM · Local web bridge
              </h2>
              <p className="mt-1 text-[11px] leading-snug text-white/50">
                One-click trusted connect uses the packaged desktop preload path — no manual pairing code here.
              </p>
            </div>
            <div className="mt-3 space-y-3">
              {gohamModalPhase === "checking" || gohamModalPhase === "connecting" ? (
                <p className="flex items-center gap-2 text-[12px] text-emerald-100/85">
                  <Loader2 className="h-4 w-4 shrink-0 animate-spin opacity-95" aria-hidden />
                  {gohamModalPhase === "checking" ? "Checking status…" : "Connecting trusted session…"}
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
          <div className="fixed right-0 top-0 z-30 flex h-full max-h-full overflow-hidden shadow-2xl md:static md:z-auto md:shadow-none">
            <WorkspaceChatInspectorPanel
              sessionId={sessionId}
              events={inspectorEvents}
              messages={messages}
              composerAttachments={attachments}
              artifactRows={artifactRows}
              executionMode={executionMode}
              onClose={() => {
                setInspectorOpen(false);
              }}
            />
          </div>
        </>
      ) : null}
    </div>
  );
}
