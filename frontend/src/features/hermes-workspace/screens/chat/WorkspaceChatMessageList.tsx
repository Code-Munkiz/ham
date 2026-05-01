/**
 * Upstream-style transcript: assistant left, user right; full-width thread (not a narrow doc column).
 */

import * as React from "react";
import { Copy, ImageDown, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { tryParseHamChatUserV1String, tryParseHamChatUserV2String } from "@/lib/ham/chatUserContent";
import { WorkspaceChatAuthImage } from "./WorkspaceChatAttachmentImage";
import { interruptedAssistantView } from "./interruptedAssistantView";

export type HwwGeneratedImageCard =
  | { kind: "loading"; promptPreview: string }
  | {
      kind: "ready";
      generatedMediaId: string;
      promptExcerpt: string;
      blobUrl: string;
      mimeType: string;
      safeDisplayName: string;
      providerLabel: string | null;
      modelId: string | null;
      width: number | null;
      height: number | null;
      generatedFromReference?: boolean;
    }
  | { kind: "error"; promptPreview: string; message: string };

export type HwwMsgRow = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
  generatedImageCard?: HwwGeneratedImageCard | null;
};

type WorkspaceChatMessageListProps = {
  messages: HwwMsgRow[];
  /** True while the last assistant message is still receiving stream deltas. */
  isStreaming?: boolean;
  /** Prefer an in-session blob/object URL before GET (mitigates flaky attachment GET on ephemeral hosts). */
  resolveLocalAttachmentPreview?: (attachmentId: string) => string | undefined;
};

export function WorkspaceChatMessageList({
  messages,
  isStreaming,
  resolveLocalAttachmentPreview,
}: WorkspaceChatMessageListProps) {
  const last = messages[messages.length - 1];
  const showThinking =
    Boolean(isStreaming && last?.role === "assistant" && !(last.content || "").trim()) &&
    !last.generatedImageCard;

  return (
    <div className="hww-chat-transcript w-full space-y-4 px-4 py-5 md:px-8 md:py-6">
      {messages.map((m, idx) => {
        if (m.role === "user") {
          const v2 = tryParseHamChatUserV2String(m.content);
          const v1 = v2 ? null : tryParseHamChatUserV1String(m.content);
          const showText = v2
            ? (v2.text || "").trim()
            : v1
              ? (v1.text || "").trim()
              : m.content.trim();
          const hasV2Media = Boolean(v2?.attachments?.length);
          const hasV1Media = Boolean(v1?.images?.length);
          return (
            <div key={m.id} className="flex justify-end">
              <div
                className={cn(
                  "max-w-[min(100%,36rem)] rounded-2xl rounded-br-md border border-white/[0.08]",
                  "bg-gradient-to-b from-white/[0.1] to-white/[0.04] px-3.5 py-2.5 text-[13px] leading-relaxed text-[#e8eef3] shadow-sm",
                )}
              >
                {v2 && v2.attachments.length > 0 ? (
                  <div className="mb-2 flex flex-wrap gap-1.5">
                    {v2.attachments.map((at, j) => (
                      <div
                        key={`${m.id}-att-${j}`}
                        className={cn(
                          at.kind === "image"
                            ? "h-20 w-28 overflow-hidden rounded-md border border-white/15 bg-black/30"
                            : "max-w-[14rem] rounded-md border border-white/12 bg-white/[0.04] px-2 py-1.5 text-left text-[11px] text-white/75",
                        )}
                      >
                        {at.kind === "image" ? (
                          <WorkspaceChatAuthImage
                            attachmentId={at.id}
                            alt={at.name || "Attachment"}
                            localPreviewUrl={resolveLocalAttachmentPreview?.(at.id)}
                          />
                        ) : at.kind === "video" ? (
                          <span className="block">
                            <span className="line-clamp-2 font-medium text-white/85">🎬 {at.name || "video"}</span>
                            <span className="mt-0.5 block text-[9px] leading-snug text-white/45">
                              Video attached — processing not enabled yet
                            </span>
                          </span>
                        ) : (
                          <span className="line-clamp-3">📄 {at.name || "file"}</span>
                        )}
                      </div>
                    ))}
                  </div>
                ) : null}
                {v1 && v1.images.length > 0 ? (
                  <div className="mb-2 flex flex-wrap gap-1.5">
                    {v1.images.map((im, j) => (
                      <div
                        key={`${m.id}-img-${j}`}
                        className="h-20 w-28 overflow-hidden rounded-md border border-white/15 bg-black/30"
                      >
                        <img
                          src={im.data_url}
                          alt={im.name || "Screenshot"}
                          className="h-full w-full object-cover"
                        />
                      </div>
                    ))}
                  </div>
                ) : null}
                {showText ? (
                  <p className="whitespace-pre-wrap break-words">{showText}</p>
                ) : hasV2Media || hasV1Media ? null : (
                  <p className="whitespace-pre-wrap break-words opacity-60">(empty message)</p>
                )}
                <p className="mt-1.5 text-right text-[10px] text-white/35">{m.timestamp}</p>
              </div>
            </div>
          );
        }
        if (m.role === "assistant") {
          const isLastAssistant = idx === messages.length - 1;
          const thinkingHere = showThinking && isLastAssistant && !m.generatedImageCard;
          const { interrupted, visibleContent } = interruptedAssistantView(m.content);
          const g = m.generatedImageCard;
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
                ) : null}

                {g?.kind === "loading" ? (
                  <div className="flex items-center gap-2 text-[12px] text-emerald-200/75" role="status">
                    <Loader2 className="h-4 w-4 animate-spin text-emerald-300/95" aria-hidden strokeWidth={2} />
                    <span>Generating image…</span>
                  </div>
                ) : null}

                {g?.kind === "error" ? (
                  <div className="rounded-md border border-red-500/25 bg-red-950/35 px-2.5 py-2 text-[12px] text-red-100/90">
                    <p className="font-medium text-red-200/95">Image generation failed</p>
                    <p className="mt-1 text-[11px] leading-snug text-red-100/80">{g.message}</p>
                    {g.promptPreview ? (
                      <p className="mt-1 line-clamp-2 text-[10px] text-red-100/55">Prompt: {g.promptPreview}</p>
                    ) : null}
                  </div>
                ) : null}

                {g?.kind === "ready" ? (
                  <div className="space-y-2">
                    <div className="overflow-hidden rounded-lg border border-white/[0.1] bg-black/25">
                      <img
                        src={g.blobUrl}
                        alt={g.promptExcerpt || "Generated image"}
                        className="max-h-[min(52vh,28rem)] w-full object-contain"
                      />
                    </div>
                    {g.promptExcerpt ? (
                      <p className="line-clamp-2 text-[11px] leading-snug text-white/45">{g.promptExcerpt}</p>
                    ) : null}
                    {g.generatedFromReference ? (
                      <p className="text-[10px] leading-snug text-white/42">Generated from reference image</p>
                    ) : null}
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-white/38">
                      {g.modelId ? (
                        <span className="rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-white/55">
                          {g.modelId}
                        </span>
                      ) : null}
                      {g.providerLabel ? <span className="text-white/40">via {g.providerLabel}</span> : null}
                      {typeof g.width === "number" && typeof g.height === "number"
                        ? `${g.width} × ${g.height}`
                        : null}
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <a
                        href={g.blobUrl}
                        download={g.safeDisplayName || "generated-image.bin"}
                        className="inline-flex items-center gap-1 rounded-md border border-emerald-500/25 bg-emerald-950/35 px-2.5 py-1 text-[11px] font-medium text-emerald-100/95 hover:bg-emerald-950/55"
                      >
                        <ImageDown className="h-3.5 w-3.5 opacity-95" aria-hidden strokeWidth={2} />
                        Download
                      </a>
                      <button
                        type="button"
                        className="inline-flex items-center gap-1 rounded-md border border-white/[0.1] px-2.5 py-1 text-[11px] font-medium text-white/70 hover:bg-white/[0.06]"
                        onClick={() => {
                          void navigator.clipboard?.writeText(g.generatedMediaId);
                        }}
                      >
                        <Copy className="h-3.5 w-3.5 opacity-85" aria-hidden strokeWidth={2} />
                        Copy asset id
                      </button>
                    </div>
                  </div>
                ) : null}

                {!thinkingHere && !g ? (
                  <>
                    <p className="whitespace-pre-wrap break-words">{visibleContent || "\u00a0"}</p>
                    {interrupted ? (
                      <p className="mt-2 text-[11px] text-amber-200/85">Connection interrupted. Ask me to continue.</p>
                    ) : null}
                  </>
                ) : null}

                {!thinkingHere && g?.kind === "ready" && visibleContent.trim() ? (
                  <p className="mt-2 whitespace-pre-wrap break-words text-white/82">{visibleContent}</p>
                ) : null}

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
