import type * as React from "react";
import { Mic, Paperclip, SendHorizontal } from "lucide-react";

type OperatorComposerProps = {
  input: string;
  sending: boolean;
  pipelineStatus: string;
  chatError: string | null;
  onInputChange: (value: string) => void;
  onSend: (event: React.FormEvent<HTMLFormElement>) => void;
};

export function OperatorComposer({
  input,
  sending,
  pipelineStatus,
  chatError,
  onInputChange,
  onSend,
}: OperatorComposerProps) {
  return (
    <div className="ow-composer-wrap shrink-0 px-3 pb-3 pt-2">
      <div className="mb-2 text-[10px] font-medium uppercase tracking-[0.12em] text-white/45">
        {pipelineStatus}
      </div>
      {chatError ? (
        <div className="mb-2 rounded-xl border border-destructive/45 bg-destructive/12 px-3 py-2 text-xs text-destructive">
          {chatError}
        </div>
      ) : null}
      <form onSubmit={onSend} className="ow-composer-shell space-y-2">
        <textarea
          value={input}
          onChange={(event) => onInputChange(event.target.value)}
          placeholder="Ask HAM operator workspace..."
          className="min-h-[88px] w-full resize-y rounded-2xl border border-white/10 bg-[#0a141f]/80 px-3 py-2 text-sm text-white outline-none placeholder:text-white/30 focus-visible:ring-2 focus-visible:ring-[#ff6b00]/45"
          disabled={sending}
        />
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled
              title="Attachment migration lands in Phase 1A.2"
              className="inline-flex items-center gap-1 rounded-full border border-white/15 bg-white/5 px-2.5 py-1 text-xs text-white/70 opacity-95"
            >
              <Paperclip className="h-3.5 w-3.5" />
              Attachment
            </button>
            <button
              type="button"
              disabled
              title="Voice migration lands in Phase 1A.2"
              className="inline-flex items-center gap-1 rounded-full border border-white/15 bg-white/5 px-2.5 py-1 text-xs text-white/70 opacity-95"
            >
              <Mic className="h-3.5 w-3.5" />
              Voice
            </button>
          </div>
          <button
            type="submit"
            disabled={sending || !input.trim()}
            className="inline-flex items-center gap-1 rounded-full bg-[#ff9a4a] px-3 py-1.5 text-xs font-semibold text-black disabled:cursor-not-allowed disabled:opacity-60"
          >
            <SendHorizontal className="h-3.5 w-3.5" />
            {sending ? "Sending..." : "Send"}
          </button>
        </div>
      </form>
    </div>
  );
}

