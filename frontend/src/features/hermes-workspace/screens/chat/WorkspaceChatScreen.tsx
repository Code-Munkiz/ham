/**
 * Workspace-native chat: upstream Hermes `ChatScreen` visual/IA pattern, HAM `/api/chat/stream` only.
 * Hermes Workspace chat only (no legacy workbench chrome).
 */

import * as React from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { PanelRight, PanelRightClose } from "lucide-react";
import { toast } from "sonner";
import {
  ensureProjectIdForWorkspaceRoot,
  fetchContextEngine,
  fetchModelsCatalog,
  HamAccessRestrictedError,
  postChatTranscribe,
  postChatUploadAttachment,
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
import { getHamDesktopLocalControlApi } from "@/lib/ham/desktopBundleBridge";
import { cn } from "@/lib/utils";
import { extractGohamUrl } from "../../goham/extractGohamUrl";
import { runGohamObserveFlow, type GoHamTrailStep } from "../../goham/gohamObserveFlow";
import { runGohamResearchFlow, shouldUseResearchLoop } from "../../goham/gohamResearchLoop";
import { GoHamPanel } from "../../goham/GoHamPanel";
import { GoHamSlice1DevPanel } from "../../goham/GoHamSlice1DevPanel";

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

export type WorkspaceChatScreenProps = {
  /** In-shell drawer: keep session off the URL; do not navigate on new session. */
  embedMode?: boolean;
};

export function WorkspaceChatScreen(props: WorkspaceChatScreenProps = {}) {
  const { embedMode = false } = props;
  const navigate = useNavigate();
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
  const [projectId, setProjectId] = React.useState<string | null>(null);
  const [attachments, setAttachments] = React.useState<WorkspaceComposerAttachment[]>([]);
  const [voiceTranscribing, setVoiceTranscribing] = React.useState(false);
  const [inspectorOpen, setInspectorOpen] = React.useState(false);
  const [inspectorEvents, setInspectorEvents] = React.useState<WorkspaceInspectorEvent[]>([]);
  const [artifactRows, setArtifactRows] = React.useState<ChatInspectorArtifactRow[]>([]);
  /** When set, deep-link effect must not call `loadFromApi` for this session while the stream turn is active. */
  const streamTurnSessionRef = React.useRef<string | null>(null);
  const gohamAbortRef = React.useRef(false);
  const gohamPausedRef = React.useRef(false);
  const gohamTakeoverRef = React.useRef(false);
  const [gohamPaused, setGohamPaused] = React.useState(false);
  const [gohamTakeover, setGohamTakeover] = React.useState(false);
  /** Slice 3 — show Pause / Resume / Take over only during an active research loop run. */
  const [gohamResearchUi, setGohamResearchUi] = React.useState(false);
  const endRef = React.useRef<HTMLDivElement | null>(null);
  const listWrapRef = React.useRef<HTMLDivElement | null>(null);

  const [gohamGateHint, setGohamGateHint] = React.useState<string | null>(null);
  const [gohamEnabled, setGohamEnabled] = React.useState(() => {
    if (typeof sessionStorage === "undefined") return false;
    return sessionStorage.getItem("hww-goham-enabled") === "1";
  });
  const [gohamTrail, setGohamTrail] = React.useState<GoHamTrailStep[]>([]);
  const [gohamActive, setGohamActive] = React.useState(false);

  const gohamEffective = gohamEnabled && !gohamGateHint;

  React.useEffect(() => {
    const api = getHamDesktopLocalControlApi();
    if (!api) {
      setGohamGateHint(
        "GoHAM Mode runs in HAM Desktop with Local Control. Use the packaged Electron app — not this browser tab.",
      );
      return;
    }
    let cancelled = false;
    void api
      .getStatus()
      .then((s) => {
        if (cancelled) return;
        if (!s.browser_real?.supported) {
          setGohamGateHint("Managed browser is unavailable here (Linux + HAM Desktop Phase 4B required).");
        } else {
          setGohamGateHint(null);
        }
      })
      .catch(() => {
        if (!cancelled) setGohamGateHint("Could not read Local Control status from HAM Desktop.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    if (gohamGateHint) {
      setGohamEnabled(false);
      try {
        sessionStorage.removeItem("hww-goham-enabled");
      } catch {
        /* ignore */
      }
    }
  }, [gohamGateHint]);

  const setGohamEnabledPersist = React.useCallback((v: boolean) => {
    setGohamEnabled(v);
    try {
      if (v) sessionStorage.setItem("hww-goham-enabled", "1");
      else sessionStorage.removeItem("hww-goham-enabled");
    } catch {
      /* ignore */
    }
  }, []);

  const voiceWs = useVoiceWorkspaceSettingsOptional();
  const sttDictationEnabled = voiceWs?.payload?.settings.stt.enabled ?? true;

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
      if (!text) {
        toast.message("No text returned from transcription.");
        return;
      }
      setInput((prev) => (prev.trim() ? `${prev.trim()}\n${text}` : text));
    } catch (err) {
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

  const handleGohamStop = React.useCallback(() => {
    gohamAbortRef.current = true;
    gohamPausedRef.current = false;
    gohamTakeoverRef.current = false;
    setGohamPaused(false);
    setGohamTakeover(false);
    setGohamResearchUi(false);
    const api = getHamDesktopLocalControlApi();
    if (api && typeof api.stopRealBrowserSession === "function") {
      void api.stopRealBrowserSession();
    }
    setGohamActive(false);
  }, []);

  const sendGohamObserve = React.useCallback(
    async (displayContent: string, url: string) => {
      const api = getHamDesktopLocalControlApi();
      if (!api) {
        toast.error("GoHAM needs HAM Desktop with Local Control.", { duration: 8000 });
        return;
      }
      gohamAbortRef.current = false;
      setGohamActive(true);
      setGohamTrail([]);
      setSending(true);
      setLoadErr(null);
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
          kind: "goham_observe_started",
          status: "info",
          summary: "GoHAM observe flow started (managed browser)",
          meta: { url_redacted: url.replace(/\?.*$/, "") },
        }),
      );
      let keepManagedBrowserOpen = false;
      try {
        const result = await runGohamObserveFlow({
          api,
          url,
          onTrail: setGohamTrail,
          shouldAbort: () => gohamAbortRef.current,
        });
        if (result.ok === true) {
          keepManagedBrowserOpen = true;
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantPlaceId ? { ...m, content: result.assistantText } : m)),
          );
          setInspectorEvents((prev) =>
            appendInspectorEvent(prev, {
              atIso: new Date().toISOString(),
              kind: "goham_observe_completed",
              status: "ok",
              summary: "GoHAM observe flow completed",
              meta: {},
            }),
          );
        } else {
          setGohamTrail(result.trailSteps);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantPlaceId
                ? {
                    ...m,
                    content: `**GoHAM could not complete this run.**\n\n${result.userMessage}\n\nThe managed browser session was stopped. You can adjust Local Control in Settings and try again.`,
                  }
                : m,
            ),
          );
          toast.error("GoHAM run failed — see message above.", { duration: 8000 });
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : "GoHAM failed unexpectedly.";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantPlaceId
              ? { ...m, content: `**GoHAM error:** ${msg}` }
              : m,
          ),
        );
        toast.error(msg, { duration: 8000 });
        void api.stopRealBrowserSession();
      } finally {
        gohamAbortRef.current = false;
        setGohamActive(keepManagedBrowserOpen);
        setSending(false);
      }
    },
    [],
  );

  const sendGohamResearch = React.useCallback(
    async (displayContent: string, url: string) => {
      const api = getHamDesktopLocalControlApi();
      if (!api) {
        toast.error("GoHAM needs HAM Desktop with Local Control.", { duration: 8000 });
        return;
      }
      gohamAbortRef.current = false;
      gohamPausedRef.current = false;
      gohamTakeoverRef.current = false;
      setGohamPaused(false);
      setGohamTakeover(false);
      setGohamResearchUi(true);
      setGohamActive(true);
      setGohamTrail([]);
      setSending(true);
      setLoadErr(null);
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
          kind: "goham_research_started",
          status: "info",
          summary: "GoHAM research loop started (managed browser)",
          meta: { url_redacted: url.replace(/\?.*$/, "") },
        }),
      );
      let keepManagedBrowserOpen = false;
      try {
        const result = await runGohamResearchFlow({
          api,
          url,
          taskText: displayContent,
          onTrail: setGohamTrail,
          shouldAbort: () => gohamAbortRef.current,
          getHoldState: () => {
            if (gohamTakeoverRef.current) return "takeover";
            if (gohamPausedRef.current) return "pause";
            return "none";
          },
        });
        if (result.ok === true) {
          keepManagedBrowserOpen = true;
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantPlaceId ? { ...m, content: result.assistantText } : m)),
          );
          setInspectorEvents((prev) =>
            appendInspectorEvent(prev, {
              atIso: new Date().toISOString(),
              kind: "goham_research_completed",
              status: "ok",
              summary: "GoHAM research loop completed",
              meta: {},
            }),
          );
        } else {
          setGohamTrail(result.trailSteps);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantPlaceId
                ? {
                    ...m,
                    content: `**GoHAM could not complete this run.**\n\n${result.userMessage}\n\nThe managed browser session was stopped. You can adjust Local Control in Settings and try again.`,
                  }
                : m,
            ),
          );
          toast.error("GoHAM run failed — see message above.", { duration: 8000 });
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : "GoHAM failed unexpectedly.";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantPlaceId ? { ...m, content: `**GoHAM error:** ${msg}` } : m,
          ),
        );
        toast.error(msg, { duration: 8000 });
        void api.stopRealBrowserSession();
      } finally {
        gohamAbortRef.current = false;
        gohamPausedRef.current = false;
        gohamTakeoverRef.current = false;
        setGohamPaused(false);
        setGohamTakeover(false);
        setGohamResearchUi(false);
        setGohamActive(keepManagedBrowserOpen);
        setSending(false);
      }
    },
    [],
  );

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
      const streamAuth: HamChatStreamAuth | undefined = await workspaceChatAdapter.getStreamAuth();
      try {
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
    [embedMode, sending, voiceTranscribing, sessionId, chatModelIdForApi, projectId, navigate],
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

    if (gohamEffective) {
      const url = extractGohamUrl(trimmed);
      if (!url) {
        toast.error(
          "GoHAM Mode needs a website in your message — e.g. https://example.com or example.com. Turn GoHAM on (amber) first; it only runs in HAM Desktop on Linux.",
          { duration: 12_000 },
        );
        return;
      }
      setInput("");
      setAttachments([]);
      if (shouldUseResearchLoop(trimmed)) {
        void sendGohamResearch(trimmed, url);
      } else {
        void sendGohamObserve(trimmed, url);
      }
      return;
    }

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
            <button
              type="button"
              onClick={startNew}
              className="shrink-0 rounded-lg border border-white/[0.1] bg-white/[0.06] px-2.5 py-1.5 text-[11px] font-medium text-[#7dd3fc] transition hover:bg-white/[0.09] hover:text-[#a5e9ff]"
            >
              New
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
        <GoHamPanel
          enabled={gohamEffective}
          active={gohamActive}
          trail={gohamTrail}
          onStop={handleGohamStop}
          gateHint={gohamGateHint}
          researchControls={
            gohamResearchUi && gohamActive
              ? {
                  paused: gohamPaused,
                  takeover: gohamTakeover,
                  onPause: () => {
                    gohamPausedRef.current = true;
                    gohamTakeoverRef.current = false;
                    setGohamPaused(true);
                    setGohamTakeover(false);
                  },
                  onResume: () => {
                    gohamPausedRef.current = false;
                    gohamTakeoverRef.current = false;
                    setGohamPaused(false);
                    setGohamTakeover(false);
                  },
                  onTakeover: () => {
                    gohamTakeoverRef.current = true;
                    gohamPausedRef.current = false;
                    setGohamTakeover(true);
                    setGohamPaused(false);
                  },
                }
              : undefined
          }
        />
        <GoHamSlice1DevPanel visible={import.meta.env.DEV && gohamEffective} />
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
            gohamEnabled={gohamEnabled}
            onGohamEnabledChange={setGohamEnabledPersist}
            gohamToggleDisabled={Boolean(gohamGateHint)}
            gohamGateHint={gohamGateHint}
          />
        </div>
      </div>
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
