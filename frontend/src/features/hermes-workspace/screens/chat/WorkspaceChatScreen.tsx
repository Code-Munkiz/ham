/**
 * Workspace-native chat: upstream Hermes `ChatScreen` visual/IA pattern, HAM `/api/chat/stream` only.
 * Does not render legacy `Chat.tsx` / OperatorWorkspace / war-room chrome.
 */

import * as React from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { toast } from "sonner";
import {
  ensureProjectIdForWorkspaceRoot,
  fetchContextEngine,
  fetchModelsCatalog,
  HamAccessRestrictedError,
} from "@/lib/ham/api";
import { CLIENT_MODEL_CATALOG_FALLBACK } from "@/lib/ham/modelCatalogFallback";
import type { ModelCatalogPayload } from "@/lib/ham/types";
import { applyHamUiActions } from "@/lib/ham/applyUiActions";
import type { HamChatStreamAuth } from "@/lib/ham/api";
import { workspaceChatAdapter, workspaceSessionAdapter } from "../../workspaceAdapters";
import { WorkspaceChatEmptyState } from "./WorkspaceChatEmptyState";
import { WorkspaceChatMessageList, type HwwMsgRow } from "./WorkspaceChatMessageList";
import { WorkspaceChatComposer } from "./WorkspaceChatComposer";
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
    } catch {
      setLoadErr("Session not found or could not be loaded.");
      setSessionId(null);
      setMessages([]);
      toast.error("Failed to load session.");
    } finally {
      setLoadingSession(false);
    }
  }, []);

  /** Deep link `?session=` */
  React.useEffect(() => {
    const s = searchParams.get("session");
    if (!s) {
      if (sessionId) {
        setSessionId(null);
        setMessages([]);
      }
      return;
    }
    if (s === sessionId) return;
    void loadFromApi(s);
  }, [searchParams, sessionId, loadFromApi]);

  const startNew = React.useCallback(() => {
    setSessionId(null);
    setMessages([]);
    setInput("");
    setLoadErr(null);
    navigate({ pathname: "/workspace/chat", search: "" }, { replace: true });
  }, [navigate]);

  React.useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages, sending]);

  const send = React.useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || sending) return;
      setInput("");
      setLoadErr(null);
      setSending(true);
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
              setSessionId(sid);
              navigate(
                { pathname: "/workspace/chat", search: `?session=${encodeURIComponent(sid)}` },
                { replace: true },
              );
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
        applyHamUiActions(res.actions ?? [], {
          navigate,
          setIsControlPanelOpen: () => {},
          isControlPanelOpen: false,
          setWorkbenchView: () => {},
        });
      } catch (err) {
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
        setSending(false);
      }
    },
    [sending, sessionId, chatModelIdForApi, projectId, navigate],
  );

  const onFormSubmit = () => {
    void send(input);
  };

  const hasTranscript = messages.length > 0;
  const showEmpty = !loadingSession && !hasTranscript && !loadErr;
  const sessionLoadFailed = Boolean(loadErr && !hasTranscript && !loadingSession);
  const crumbTitle = !sessionId ? "New" : shortId(sessionId, 10);

  return (
    <div className="flex min-h-0 w-full min-w-0 flex-1 flex-col">
      <div className="hww-chat-breadcrumb shrink-0 border-b border-white/[0.06] bg-[#040d14]/50 px-3 py-2.5 md:px-4">
        <div className="mx-auto flex max-w-3xl items-center gap-1 text-[12px] text-white/50">
          <span className="text-white/35">Hermes Workspace</span>
          <ChevronRight className="h-3.5 w-3.5 shrink-0 opacity-50" aria-hidden />
          <span className="font-medium text-white/75">{crumbTitle}</span>
          {sessionId ? (
            <button
              type="button"
              onClick={startNew}
              className="ml-2 text-[11px] text-[#7dd3fc] underline decoration-white/10 underline-offset-2 hover:decoration-[#7dd3fc]/50"
            >
              New session
            </button>
          ) : null}
        </div>
      </div>
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
            <WorkspaceChatMessageList messages={messages} />
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
        catalog={catalog}
        modelId={modelId}
        onModelIdChange={setModelId}
      />
    </div>
  );
}
