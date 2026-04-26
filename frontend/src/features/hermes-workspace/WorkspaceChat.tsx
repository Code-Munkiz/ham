import * as React from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, MessageSquare, Search, Send } from "lucide-react";
import { HamAccessRestrictedError } from "@/lib/ham/api";
import { workspaceChatAdapter } from "./workspaceAdapters";
import type { WorkspaceChatMessage } from "./workspaceTypes";

function timeStr(): string {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

const DEFAULT_WORKBENCH_MODE: "ask" | "plan" | "agent" = "agent";
const DEFAULT_WORKER = "builder";

/**
 * HAM-wired namespaced chat: same stream contract as `/chat`, routed through `workspaceChatAdapter` only.
 */
export function WorkspaceChat() {
  const [sessionId, setSessionId] = React.useState<string | null>(null);
  const [input, setInput] = React.useState("");
  const [messages, setMessages] = React.useState<WorkspaceChatMessage[]>([]);
  const [sending, setSending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [gatewayCode, setGatewayCode] = React.useState<string | null>(null);
  const bottomRef = React.useRef<HTMLDivElement>(null);

  const hasThread = messages.length > 0;

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages, sending]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || sending) return;

    setInput("");
    setError(null);
    setGatewayCode(null);

    const userRow: WorkspaceChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: text,
      timestamp: timeStr(),
    };
    const assistantPlaceId = `assist-pending-${Date.now()}`;
    const assistantRow: WorkspaceChatMessage = {
      id: assistantPlaceId,
      role: "assistant",
      content: "",
      timestamp: timeStr(),
    };
    setMessages((prev) => [...prev, userRow, assistantRow]);
    setSending(true);

    try {
      const streamAuth = await workspaceChatAdapter.getStreamAuth();
      const res = await workspaceChatAdapter.stream(
        {
          session_id: sessionId ?? undefined,
          messages: [{ role: "user", content: text }],
          workbench_mode: DEFAULT_WORKBENCH_MODE,
          worker: DEFAULT_WORKER,
        },
        {
          onSession: (sid) => setSessionId(sid),
          onDelta: (delta) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantPlaceId ? { ...m, content: m.content + delta } : m,
              ),
            );
          },
        },
        streamAuth,
      );

      setSessionId(res.session_id);
      if (res.gateway_error?.code) {
        setGatewayCode(res.gateway_error.code);
      }
      setMessages(
        res.messages.map((m, i) => ({
          id: `${res.session_id}-${i}-${m.role}`,
          role: m.role,
          content: m.content,
          timestamp: timeStr(),
        })),
      );
    } catch (err) {
      if (err instanceof HamAccessRestrictedError) {
        setError(
          "Access restricted: this Ham deployment only allows approved email addresses or domains. Ask an admin or check Clerk sign-up restrictions.",
        );
        return;
      }
      if (err instanceof Error && err.message === "Chat stream ended without a done event") {
        setError("Response was interrupted — partial text above is preserved on the server when possible.");
        return;
      }
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 w-full min-w-0 flex-col overflow-hidden md:flex-row">
      {/* Session rail (placeholder; real list in a later commit) */}
      <aside className="flex max-h-36 w-full shrink-0 flex-col border-b border-[color:var(--ham-workspace-line)] bg-[#040d12]/50 p-3 md:max-h-none md:w-56 md:border-b-0 md:border-r">
        <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-white/40">
          This session
        </p>
        <div className="hww-session-placeholder mb-2">
          {sessionId ? (
            <span className="block truncate font-mono text-[10px] text-white/50" title={sessionId}>
              {sessionId}
            </span>
          ) : (
            "New — history rail next"
          )}
        </div>
        <div className="relative mb-2">
          <Search
            className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-white/30"
            strokeWidth={1.5}
          />
          <input
            type="search"
            readOnly
            placeholder="Message search…"
            className="hww-input w-full cursor-default rounded-md py-1.5 pl-7 text-[11px]"
            title="Tied to session transcript index in a later commit"
          />
        </div>
        <p className="text-[11px] leading-relaxed text-white/40">
          Session list will share the HAM model with <span className="font-mono">/chat</span>.
        </p>
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="shrink-0 border-b border-[color:var(--ham-workspace-line)] bg-[#040d14]/50 px-4 py-3 md:px-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-white/50" strokeWidth={1.5} />
              <h2 className="text-sm font-semibold text-white/90">Workspace chat</h2>
            </div>
            <span className="hww-pill">
              {sending ? "Streaming…" : workspaceChatAdapter.ready ? "HAM stream" : "off"}
            </span>
          </div>
          <p className="mt-1.5 text-[12px] text-white/42">{workspaceChatAdapter.description}</p>
        </header>

        {error ? (
          <div
            className="mx-3 mt-3 flex shrink-0 items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-950/50 px-3 py-2 text-[12px] text-amber-100/90 md:mx-4"
            role="alert"
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300/80" />
            <span className="min-w-0 flex-1 leading-snug">{error}</span>
          </div>
        ) : null}

        {gatewayCode ? (
          <div
            className="mx-3 mt-2 flex shrink-0 items-center gap-2 rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-[11px] text-white/60 md:mx-4"
            role="status"
          >
            <span className="text-white/45">Model gateway note:</span>
            <code className="font-mono text-white/70">{gatewayCode}</code>
            <span className="text-white/40">(final copy is in the message above)</span>
          </div>
        ) : null}

        <div className="hww-scroll min-h-0 flex-1 overflow-y-auto px-3 py-4 md:px-5">
          {!hasThread ? (
            <div className="mx-auto flex min-h-[min(60vh,420px)] max-w-md flex-col items-center justify-center rounded-2xl border border-[color:var(--ham-workspace-line)] bg-[#040d14]/40 p-6 text-center">
              <p className="text-[15px] font-medium text-white/70">Start a HAM turn</p>
              <p className="mt-2 text-[13px] leading-relaxed text-white/45">
                Messages stream from the same <span className="font-mono text-white/55">/api/chat/stream</span> contract
                as the main chat — no browser-side Hermes proxy.
              </p>
              <Link
                to="/workspace"
                className="mt-5 text-[12px] font-medium text-[#ffb27a]/90 hover:text-[#ffc896]"
              >
                ← Workspace home
              </Link>
            </div>
          ) : (
            <ul className="mx-auto flex max-w-3xl flex-col gap-3 pb-2">
              {messages.map((m) => {
                if (m.role === "user") {
                  return (
                    <li key={m.id} className="flex justify-end">
                      <div
                        className="max-w-[min(100%,32rem)] rounded-2xl border border-white/10 bg-white/[0.08] px-3.5 py-2.5 text-[13px] leading-relaxed text-white/90"
                        data-role="user"
                      >
                        <p className="whitespace-pre-wrap break-words">{m.content}</p>
                        <p className="mt-1.5 text-[9px] uppercase tracking-wider text-white/30">{m.timestamp}</p>
                      </div>
                    </li>
                  );
                }
                if (m.role === "assistant") {
                  return (
                    <li key={m.id} className="flex justify-start">
                      <div
                        className="max-w-[min(100%,40rem)] rounded-2xl border border-[color:var(--ham-workspace-line)] bg-[#040d10]/80 px-3.5 py-2.5 text-[13px] leading-relaxed text-white/[0.88]"
                        data-role="assistant"
                      >
                        {m.content ? (
                          <p className="whitespace-pre-wrap break-words">{m.content}</p>
                        ) : sending ? (
                          <p className="text-white/35">…</p>
                        ) : null}
                        <p className="mt-1.5 text-[9px] uppercase tracking-wider text-white/25">{m.timestamp}</p>
                      </div>
                    </li>
                  );
                }
                return (
                  <li key={m.id} className="text-center">
                    <p className="text-[11px] text-white/40">
                      <span className="font-mono">[system]</span> {m.content}
                    </p>
                  </li>
                );
              })}
              <div ref={bottomRef} />
            </ul>
          )}
        </div>

        <div className="shrink-0 border-t border-[color:var(--ham-workspace-line)] bg-[#040d12]/60 px-3 py-3 md:px-4">
          <div className="mx-auto flex max-w-3xl items-end gap-2">
            <label className="sr-only" htmlFor="hww-workspace-composer">
              Message
            </label>
            <textarea
              id="hww-workspace-composer"
              rows={1}
              value={input}
              disabled={sending}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void handleSend();
                }
              }}
              placeholder="Message… (Enter to send, Shift+Enter for newline)"
              className="hww-input max-h-32 min-h-[44px] flex-1 resize-y rounded-lg px-3 py-2.5 text-[13px] leading-relaxed"
            />
            <button
              type="button"
              disabled={sending || !input.trim()}
              onClick={() => void handleSend()}
              className="inline-flex h-11 shrink-0 items-center justify-center gap-1.5 rounded-lg border border-white/12 bg-white/[0.08] px-3 text-[12px] font-medium text-white/80 transition hover:border-white/20 hover:bg-white/[0.12] disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Send className="h-4 w-4" strokeWidth={1.5} />
              <span className="hidden sm:inline">Send</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
