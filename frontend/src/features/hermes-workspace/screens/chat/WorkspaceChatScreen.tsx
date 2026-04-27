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
} from "@/lib/ham/api";
import { CLIENT_MODEL_CATALOG_FALLBACK } from "@/lib/ham/modelCatalogFallback";
import type { ModelCatalogPayload } from "@/lib/ham/types";
import { applyHamUiActions } from "@/lib/ham/applyUiActions";
import type { HamChatStreamAuth } from "@/lib/ham/api";
import { workspaceChatAdapter, workspaceSessionAdapter } from "../../workspaceAdapters";
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
  buildOutboundMessageWithAttachments,
  fileToWorkspaceAttachment,
  formatAttachmentByteSize,
  MAX_WORKSPACE_ATTACHMENT_BYTES,
  MAX_WORKSPACE_ATTACHMENT_COUNT,
  type WorkspaceComposerAttachment,
} from "./composerAttachmentHelpers";
import { cn } from "@/lib/utils";

function timeStr() {
  return new Date().toLocaleTimeString([], {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function shortId(id: string, n = 8) {
  return id.length <= n ? id : `${id.slice(0, n)}…`;
}

export function WorkspaceChatScreen() {
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
  /** When set, deep-link effect must not call `loadFromApi` for this session while the stream turn is active. */
  const streamTurnSessionRef = React.useRef<string | null>(null);
  const endRef = React.useRef<HTMLDivElement | null>(null);
  const listWrapRef = React.useRef<HTMLDivElement | null>(null);

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

  const loadFromApi = React.useCallback(async (sid: string) => {
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
      setLoadErr("Session not found or could not be loaded.");
      setSessionId(null);
      setMessages([]);
      setInspectorEvents([]);
      toast.error("Failed to load session.");
    } finally {
      setLoadingSession(false);
    }
  }, []);

  /** Deep link `?session=` */
  React.useEffect(() => {
    const s = searchParams.get("session");
    if (!s) {
      streamTurnSessionRef.current = null;
      if (sessionId) {
        setSessionId(null);
        setMessages([]);
        setInspectorEvents([]);
      }
      return;
    }
    if (s === sessionId) return;
    if (sending && streamTurnSessionRef.current === s) {
      return;
    }
    void loadFromApi(s);
  }, [searchParams, sessionId, sending, loadFromApi]);

  const startNew = React.useCallback(() => {
    setSessionId(null);
    setMessages([]);
    setInspectorEvents([]);
    setInput("");
    setAttachments([]);
    setLoadErr(null);
    navigate({ pathname: "/workspace/chat", search: "" }, { replace: true });
  }, [navigate]);

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
        } else {
          next.push(a);
        }
      } catch {
        toast.error(`Could not read “${f.name || "file"}”.`);
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

  const send = React.useCallback(
    async (outboundUserMessage: string) => {
      const trimmed = outboundUserMessage.trim();
      if (!trimmed || sending || voiceTranscribing) return;
      setInput("");
      setAttachments([]);
      setLoadErr(null);
      setSending(true);
      streamTurnSessionRef.current = null;
      const priorSession = sessionId;
      const userRow: HwwMsgRow = {
        id: `hww-user-${Date.now()}`,
        role: "user",
        content: trimmed,
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
          summary: `User message sent (${trimmed.length} character${trimmed.length === 1 ? "" : "s"})`,
          meta: { message_id: userRow.id, char_count: trimmed.length },
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
            messages: [{ role: "user", content: trimmed }],
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
              navigate(
                { pathname: "/workspace/chat", search: `?session=${encodeURIComponent(sid)}` },
                { replace: true },
              );
              setInspectorEvents((prev) => {
                const patched = patchInspectorEventsSessionId(prev, sid);
                if (sid === priorSession) return patched;
                return appendInspectorEvent(patched, {
                  atIso: new Date().toISOString(),
                  kind: "session_assigned",
                  status: "ok",
                  summary: `Session assigned (${sid.slice(0, 8)}…)`,
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
    [sending, voiceTranscribing, sessionId, chatModelIdForApi, projectId, navigate],
  );

  const onFormSubmit = () => {
    const trimmed = input.trim();
    const outbound = buildOutboundMessageWithAttachments(trimmed, attachments);
    if (!outbound.trim() || voiceTranscribing) return;
    void send(outbound);
  };

  const hasTranscript = messages.length > 0;
  const showEmpty = !loadingSession && !hasTranscript && !loadErr;
  const sessionLoadFailed = Boolean(loadErr && !hasTranscript && !loadingSession);
  const headerTitle = !sessionId ? "New session" : "Chat";
  const last = messages[messages.length - 1];
  const isStreaming =
    sending && last?.role === "assistant" && !(last?.content || "").trim();

  return (
    <div className="flex min-h-0 w-full min-w-0 flex-1 flex-col md:flex-row">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="hww-chat-header flex shrink-0 items-start justify-between gap-3 border-b border-white/[0.06] bg-[#040d14]/80 px-4 py-3 backdrop-blur-sm md:px-8">
          <div className="min-w-0">
            <h1 className="text-[15px] font-semibold tracking-tight text-white/[0.95]">{headerTitle}</h1>
            <p className="mt-0.5 truncate font-mono text-[11px] text-white/40" title={sessionId ?? undefined}>
              {sessionId ? shortId(sessionId, 12) : "No session selected · messages stay on-device via HAM"}
            </p>
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
              <span className="font-mono text-[10px] text-white/60">{"{ }"}</span>
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
            <div className="flex flex-1 flex-col items-center justify-center gap-3 px-4 py-12 text-center">
              <p className="max-w-sm text-sm text-amber-200/90">{loadErr}</p>
              <button
                type="button"
                onClick={startNew}
                className="text-[13px] text-[#7dd3fc] underline decoration-white/10 underline-offset-2"
              >
                Start new session
              </button>
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
        />
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
