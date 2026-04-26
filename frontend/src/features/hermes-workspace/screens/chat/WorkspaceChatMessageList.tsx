/**
 * Upstream-style transcript: assistant left, user right; no HAM war-room / operator chrome.
 */

import * as React from "react";
import { cn } from "@/lib/utils";

export type HwwMsgRow = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
};

type WorkspaceChatMessageListProps = {
  messages: HwwMsgRow[];
};

export function WorkspaceChatMessageList({ messages }: WorkspaceChatMessageListProps) {
  return (
    <div className="hww-chat-transcript mx-auto w-full max-w-3xl space-y-4 px-3 py-4 md:px-4">
      {messages.map((m) => {
        if (m.role === "user") {
          return (
            <div key={m.id} className="flex justify-end">
              <div
                className={cn(
                  "max-w-[min(100%,32rem)] rounded-2xl rounded-br-sm border border-white/[0.08]",
                  "bg-gradient-to-b from-white/[0.1] to-white/[0.04] px-3.5 py-2.5 text-[13px] leading-relaxed text-[#e8eef3]",
                )}
              >
                <p className="whitespace-pre-wrap break-words">{m.content}</p>
                <p className="mt-1.5 text-right text-[10px] text-white/35">{m.timestamp}</p>
              </div>
            </div>
          );
        }
        if (m.role === "assistant") {
          return (
            <div key={m.id} className="flex justify-start">
              <div
                className={cn(
                  "max-w-[min(100%,40rem)] rounded-2xl rounded-bl-sm border border-white/[0.06]",
                  "bg-[#060f16]/80 px-3.5 py-2.5 text-[13px] leading-relaxed text-[#d0dce8]",
                )}
              >
                <p className="whitespace-pre-wrap break-words">{m.content || "\u00a0"}</p>
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
