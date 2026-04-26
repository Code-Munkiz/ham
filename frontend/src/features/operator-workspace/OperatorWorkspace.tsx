import * as React from "react";
import { ChevronRight, Menu, Plus, Search, X } from "lucide-react";
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

const QUICK_CHIPS = [
  "Analyze workspace",
  "Save a preference",
  "Create a file",
];

export function OperatorWorkspace({
  activeAgentNote,
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
  const emptyState = messages.length === 0;

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
          {activeAgentNote ? (
            <span className="hidden max-w-[32ch] truncate text-[11px] text-emerald-300 md:inline">
              {activeAgentNote}
            </span>
          ) : null}
          <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.8)]" />
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
            <button
              type="button"
              className="ow-search"
              onClick={onOpenHistory}
            >
              <Search className="h-3.5 w-3.5" />
              Search
            </button>
            <button
              type="button"
              onClick={onStartNewChat}
              className="ow-new-session"
            >
              <Plus className="h-3.5 w-3.5" />
              New Session
            </button>
          </div>
          <div className="ow-sidebar-list">
            {sessions.length === 0 ? (
              <p className="text-[11px] text-white/40">
                No sessions yet. Start a conversation.
              </p>
            ) : (
              sessions.map((session) => (
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
                  <span className="truncate text-left text-[11px] font-medium">
                    {session.preview || "Untitled session"}
                  </span>
                  <span className="text-[10px] text-white/45">
                    {session.turnCount} msg
                  </span>
                </button>
              ))
            )}
          </div>
        </aside>

        <section className="ow-main">
          {emptyState ? (
            <div className="ow-empty-state">
              <div className="ow-empty-avatar">H</div>
              <p className="ow-empty-overline">Hermes Workspace</p>
              <h2 className="ow-empty-title">Begin a session</h2>
              <p className="ow-empty-subtitle">
                Agent chat, live tools, memory, and observability.
              </p>
              <div className="ow-empty-chips">
                {QUICK_CHIPS.map((chip) => (
                  <button
                    key={chip}
                    type="button"
                    className="ow-chip"
                    onClick={() => onInputChange(chip)}
                  >
                    {chip}
                  </button>
                ))}
              </div>
            </div>
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

