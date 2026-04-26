import * as React from "react";
import { motion } from "motion/react";
import { Brain, ChevronRight, Code, Menu, Plus, Puzzle, Search, X, type LucideIcon } from "lucide-react";
import { publicAssetUrl } from "@/lib/ham/publicAssets";
import { OperatorComposer } from "./OperatorComposer";
import { OperatorMessageList } from "./OperatorMessageList";
import type { OperatorAttachment, OperatorMessage, OperatorSessionItem } from "./types";
import "./operatorWorkspace.css";

type OperatorWorkspaceProps = {
  activeAgentNote: string | null;
  activeProjectName: string;
  messages: OperatorMessage[];
  sessions: OperatorSessionItem[];
  input: string;
  sending: boolean;
  voiceTranscribing: boolean;
  pipelineStatus: string;
  chatError: string | null;
  attachment: OperatorAttachment | null;
  attachmentAccept: string;
  onInputChange: (value: string) => void;
  onAttachmentSelect: (file: File) => void;
  onAttachmentClear: () => void;
  onDictationText: (text: string) => void;
  onVoiceBlob: (blob: Blob) => void;
  onVoiceError: (message: string) => void;
  onSend: (event: React.FormEvent<HTMLFormElement>) => void;
  onOpenHistory: () => void;
  onStartNewChat: () => void;
  onSelectSession: (sessionId: string) => void;
};

/** Repomix `chat-empty-state.tsx` SUGGESTIONS — labels + full prompts. */
const HERMES_EMPTY_SUGGESTIONS: { label: string; prompt: string; Icon: LucideIcon }[] = [
  {
    label: "Analyze workspace",
    prompt:
      "Analyze this workspace structure and give me 3 engineering risks. Use tools and keep it concise.",
    Icon: Code,
  },
  {
    label: "Save a preference",
    prompt:
      'Save this to memory exactly: "For demos, respond in 3 bullets max and put risk first." Then confirm saved.',
    Icon: Brain,
  },
  {
    label: "Create a file",
    prompt: "Create demo-checklist.md with 5 launch checks for this app.",
    Icon: Puzzle,
  },
];

function formatSessionMeta(createdAt: string | null): string | null {
  if (!createdAt) return null;
  try {
    const d = new Date(createdAt);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return null;
  }
}

export function OperatorWorkspace({
  activeAgentNote: _activeAgentNote,
  activeProjectName,
  messages,
  sessions,
  input,
  sending,
  voiceTranscribing,
  pipelineStatus,
  chatError,
  attachment,
  attachmentAccept,
  onInputChange,
  onAttachmentSelect,
  onAttachmentClear,
  onDictationText,
  onVoiceBlob,
  onVoiceError,
  onSend,
  onOpenHistory,
  onStartNewChat,
  onSelectSession,
}: OperatorWorkspaceProps) {
  const [mobileSidebarOpen, setMobileSidebarOpen] = React.useState(false);
  const [sessionQuery, setSessionQuery] = React.useState("");
  const emptyState = messages.length === 0;

  const visibleSessions = React.useMemo(() => {
    const q = sessionQuery.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter(
      (s) =>
        (s.preview || "").toLowerCase().includes(q) ||
        s.sessionId.toLowerCase().includes(q),
    );
  }, [sessions, sessionQuery]);

  return (
    <div className="ow-root">
      <header className="ow-header">
        <div className="flex min-w-0 items-center gap-2">
          <button
            type="button"
            className="ow-mobile-sidebar-btn"
            onClick={() => setMobileSidebarOpen(true)}
            aria-label="Open workspace sessions"
          >
            <Menu className="h-4 w-4" />
          </button>
          <p className="ow-kicker">Hermes Workspace</p>
          <ChevronRight className="h-3.5 w-3.5 text-white/35" />
          <p className="truncate text-xs text-white/65">
            {activeProjectName || "new"}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Active agent / builder notes deferred from visible Workspace frame — state still lives in Chat.tsx. */}
          <span className="h-2 w-2 rounded-full bg-emerald-400/90 shadow-[0_0_10px_rgba(16,185,129,0.55)]" title="Session active" />
        </div>
      </header>

      <div className="ow-grid">
        {mobileSidebarOpen ? (
          <button
            type="button"
            className="ow-mobile-sidebar-backdrop"
            aria-label="Close workspace sessions"
            onClick={() => setMobileSidebarOpen(false)}
          />
        ) : null}

        <aside className={`ow-sidebar ${mobileSidebarOpen ? "is-mobile-open" : ""}`}>
          <div className="ow-sidebar-head">
            <div className="ow-sidebar-topline">
              <span className="text-[10px] uppercase tracking-[0.15em] text-white/45">
                Sessions
              </span>
              <button
                type="button"
                className="ow-sidebar-close"
                onClick={() => setMobileSidebarOpen(false)}
                aria-label="Close workspace sessions"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
            <label className="ow-search-field" htmlFor="ow-session-search">
              <span className="ow-search-field-inner">
                <Search className="h-3.5 w-3.5 shrink-0 text-white/35" aria-hidden />
                <input
                  id="ow-session-search"
                  type="search"
                  value={sessionQuery}
                  onChange={(e) => setSessionQuery(e.target.value)}
                  placeholder="Filter sessions"
                  className="ow-search-input"
                  autoComplete="off"
                  spellCheck={false}
                />
              </span>
            </label>
            <button
              type="button"
              onClick={onStartNewChat}
              className="ow-new-session"
            >
              <Plus className="h-3.5 w-3.5" />
              New session
            </button>
          </div>
          <div className="ow-sidebar-list">
            {sessions.length === 0 ? (
              <p className="text-[11px] text-white/40">
                No sessions yet. Start a conversation.
              </p>
            ) : visibleSessions.length === 0 ? (
              <p className="text-[11px] text-white/38">No sessions match that filter.</p>
            ) : (
              visibleSessions.map((session) => {
                const dateLabel = formatSessionMeta(session.createdAt);
                return (
                <button
                  key={session.sessionId}
                  type="button"
                  onClick={() => {
                    onSelectSession(session.sessionId);
                    setMobileSidebarOpen(false);
                  }}
                  className={`ow-session-btn ${session.isActive ? "is-active" : ""}`}
                  title={session.preview || session.sessionId}
                >
                  <span className="ow-session-text">
                    <span className="ow-session-title truncate text-left text-[11px] font-medium">
                      {session.preview || "Untitled session"}
                    </span>
                    <span className="ow-session-meta">
                      {dateLabel ? (
                        <span className="text-[10px] text-white/35">{dateLabel}</span>
                      ) : null}
                      <span className="text-[10px] text-white/45">
                        {session.turnCount} msg
                      </span>
                    </span>
                  </span>
                </button>
                );
              })
            )}
            {sessions.length > 0 ? (
              <button
                type="button"
                onClick={onOpenHistory}
                className="ow-sidebar-more"
              >
                View all in panel
              </button>
            ) : null}
          </div>
        </aside>

        <section className="ow-main">
          {emptyState ? (
            <motion.div
              className="ow-empty-state"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: "easeOut" }}
            >
              <div className="ow-empty-hermes-avatar">
                <img
                  src={publicAssetUrl("ham-logo.png")}
                  alt=""
                  className="ow-empty-hermes-img"
                />
              </div>
              <p className="ow-empty-overline">Hermes Workspace</p>
              <h2 className="ow-empty-title">Begin a session</h2>
              <p className="ow-empty-subline">Agent chat · live tools · memory · full observability</p>
              <p className="ow-empty-subtitle">
                Type below to start. Your project context is applied on the server.
              </p>
              <div className="ow-empty-chips">
                {HERMES_EMPTY_SUGGESTIONS.map(({ label, prompt, Icon }) => (
                  <button
                    key={label}
                    type="button"
                    className="ow-chip ow-chip-hermes"
                    onClick={() => onInputChange(prompt)}
                    title={label}
                  >
                    <Icon className="h-3.5 w-3.5 shrink-0 text-[#5eead4]/90" strokeWidth={1.5} />
                    <span className="truncate">{label}</span>
                  </button>
                ))}
              </div>
            </motion.div>
          ) : (
            <OperatorMessageList messages={messages} />
          )}
          <OperatorComposer
            input={input}
            sending={sending}
            voiceTranscribing={voiceTranscribing}
            pipelineStatus={pipelineStatus}
            chatError={chatError}
            attachment={attachment}
            attachmentAccept={attachmentAccept}
            onInputChange={onInputChange}
            onAttachmentSelect={onAttachmentSelect}
            onAttachmentClear={onAttachmentClear}
            onDictationText={onDictationText}
            onVoiceBlob={onVoiceBlob}
            onVoiceError={onVoiceError}
            onSend={onSend}
          />
        </section>
      </div>
    </div>
  );
}

