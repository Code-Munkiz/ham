/**
 * Upstream-style transcript: assistant left, user right; full-width thread (not a narrow doc column).
 */

import * as React from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export type HwwMsgRow = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
};

type WorkspaceChatMessageListProps = {
  messages: HwwMsgRow[];
  /** True while the last assistant message is still receiving stream deltas. */
  isStreaming?: boolean;
};

export function WorkspaceChatMessageList({ messages, isStreaming }: WorkspaceChatMessageListProps) {
  const last = messages[messages.length - 1];
  const showThinking =
    Boolean(isStreaming && last?.role === "assistant" && !(last.content || "").trim());

  return (
    <div className="hww-chat-transcript w-full space-y-4 px-4 py-5 md:px-8 md:py-6">
      {messages.map((m, idx) => {
        if (m.role === "user") {
          return (
            <div key={m.id} className="flex justify-end">
              <div
                className={cn(
                  "max-w-[min(100%,36rem)] rounded-2xl rounded-br-md border border-white/[0.08]",
                  "bg-gradient-to-b from-white/[0.1] to-white/[0.04] px-3.5 py-2.5 text-[13px] leading-relaxed text-[#e8eef3] shadow-sm",
                )}
              >
                <p className="whitespace-pre-wrap break-words">{m.content}</p>
                <p className="mt-1.5 text-right text-[10px] text-white/35">{m.timestamp}</p>
              </div>
            </div>
          );
        }
        if (m.role === "assistant") {
          const isLastAssistant = idx === messages.length - 1;
          const thinkingHere = showThinking && isLastAssistant;
          return (
            <div key={m.id} className="flex justify-start">
              <div
                className={cn(
                  "max-w-[min(100%,48rem)] rounded-2xl rounded-bl-md border border-white/[0.07]",
                  "bg-[#060f16]/85 px-3.5 py-2.5 text-[13px] leading-relaxed text-[#d0dce8] shadow-sm",
                )}
              >
                {thinkingHere ? (
                  <div className="flex items-center gap-2 text-[12px] text-white/45">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={2} />
                    <span>Thinking…</span>
                  </div>
                ) : (
                  <p className="whitespace-pre-wrap break-words">{m.content || "\u00a0"}</p>
                )}
                <p className="mt-1.5 text-[10px] text-white/30">{m.timestamp}</p>
              </div>
            </div>
          );
        }
        return (
          <div key={m.id} className="text-center text-[12px] text-amber-200/80">
            <p className="whitespace-pre-wrap rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2">
              {m.content}
            </p>
            <p className="mt-1 text-[10px] text-white/30">{m.timestamp}</p>
          </div>
        );
      })}
    </div>
  );
}
