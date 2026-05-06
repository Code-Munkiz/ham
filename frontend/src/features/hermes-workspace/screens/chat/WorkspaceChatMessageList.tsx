/**
 * Upstream-style transcript: assistant left, user right; full-width thread (not a narrow doc column).
 */

import * as React from "react";
import { Clapperboard, Copy, ImageDown, Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import {
  tryParseHamChatUserV1String,
  tryParseHamChatUserV2String,
} from "@/lib/ham/chatUserContent";
import { WorkspaceChatAuthImage } from "./WorkspaceChatAttachmentImage";
import { interruptedAssistantView } from "./interruptedAssistantView";

async function copyToClipboard(label: string, text: string): Promise<void> {
  const t = text.replace(/\r\n/g, "\n").trim();
  if (!t) {
    toast.error("Nothing to copy.");
    return;
  }
  try {
    if (!navigator.clipboard?.writeText) {
      toast.error("Could not copy to clipboard.");
      return;
    }
    await navigator.clipboard.writeText(t);
    toast.success(`${label} copied`);
  } catch {
    toast.error("Could not copy to clipboard.");
  }
}

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

export type HwwGeneratedVideoCard =
  | { kind: "loading"; promptPreview: string; phase: "queued" | "running" }
  | {
      kind: "ready";
      generatedMediaId: string;
      promptExcerpt: string;
      blobUrl: string;
      mimeType: string;
      safeDisplayName: string;
      providerLabel: string | null;
      modelId: string | null;
    }
  | { kind: "error"; promptPreview: string; message: string };

export type HwwMsgRow = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
  generatedImageCard?: HwwGeneratedImageCard | null;
  generatedVideoCard?: HwwGeneratedVideoCard | null;
};

type WorkspaceChatMessageListProps = {
  messages: HwwMsgRow[];
  /** True while the last assistant message is still receiving stream deltas. */
  isStreaming?: boolean;
  /** Prefer an in-session blob/object URL before GET (mitigates flaky attachment GET on ephemeral hosts). */
  resolveLocalAttachmentPreview?: (attachmentId: string) => string | undefined;
  /** Drops the assistant image card from view (blob URL revoked); does not mutate server-side session rows. */
  onRemoveGeneratedImage?: (assistantMessageId: string) => void;
  onRemoveGeneratedVideo?: (assistantMessageId: string) => void;
};

function IconTextButton(props: {
  label: string;
  onClick: () => void;
  icon: React.ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex items-center gap-1 rounded-md border border-white/[0.08] px-1.5 py-0.5 text-[10px] font-medium text-white/55 hover:bg-white/[0.06] hover:text-white/80",
        props.className,
      )}
      aria-label={props.label}
      title={props.label}
      onClick={props.onClick}
    >
      {props.icon}
      <span className="max-md:sr-only">{props.label}</span>
    </button>
  );
}

export function WorkspaceChatMessageList({
  messages,
  isStreaming,
  resolveLocalAttachmentPreview,
  onRemoveGeneratedImage,
  onRemoveGeneratedVideo,
}: WorkspaceChatMessageListProps) {
  const last = messages[messages.length - 1];
  const showThinking =
    Boolean(isStreaming && last?.role === "assistant" && !(last.content || "").trim()) &&
    !last.generatedImageCard &&
    !last.generatedVideoCard;

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
          const canCopyUser = showText.length > 0;
          return (
            <div key={m.id} className="flex justify-end">
              <div className="flex max-w-[min(100%,36rem)] flex-col items-stretch gap-1">
                <div
                  className={cn(
                    "rounded-2xl rounded-br-md border border-white/[0.08]",
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
                              <span className="line-clamp-2 font-medium text-white/85">
                                🎬 {at.name || "video"}
                              </span>
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
                {canCopyUser ? (
                  <div className="flex justify-end gap-1">
                    <IconTextButton
                      label="Copy"
                      icon={<Copy className="h-3 w-3 opacity-85" aria-hidden strokeWidth={2} />}
                      onClick={() => {
                        void copyToClipboard("Message", showText);
                      }}
                    />
                  </div>
                ) : null}
              </div>
            </div>
          );
        }
        if (m.role === "assistant") {
          const isLastAssistant = idx === messages.length - 1;
          const thinkingHere =
            showThinking && isLastAssistant && !m.generatedImageCard && !m.generatedVideoCard;
          const { interrupted, visibleContent } = interruptedAssistantView(m.content);
          const gImage = m.generatedImageCard;
          const gVideo = m.generatedVideoCard;
          const assistantTextToCopy = visibleContent.trim();
          const canCopyAssistantPlain =
            !thinkingHere && !gImage && !gVideo && assistantTextToCopy.length > 0;
          const canCopyImagePrompt =
            gImage?.kind === "ready" && (gImage.promptExcerpt || "").trim().length > 0;
          const canCopyVideoPrompt =
            gVideo?.kind === "ready" && (gVideo.promptExcerpt || "").trim().length > 0;
          return (
            <div key={m.id} className="flex justify-start">
              <div className="flex max-w-[min(100%,48rem)] flex-col items-stretch gap-1">
                <div
                  className={cn(
                    "rounded-2xl rounded-bl-md border border-white/[0.07]",
                    "bg-[#060f16]/85 px-3.5 py-2.5 text-[13px] leading-relaxed text-[#d0dce8] shadow-sm",
                  )}
                >
                  {thinkingHere ? (
                    <div className="flex items-center gap-2 text-[12px] text-white/45">
                      <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={2} />
                      <span>Thinking…</span>
                    </div>
                  ) : null}

                  {gImage?.kind === "loading" ? (
                    <div
                      className="flex items-center gap-2 text-[12px] text-emerald-200/75"
                      role="status"
                    >
                      <Loader2
                        className="h-4 w-4 animate-spin text-emerald-300/95"
                        aria-hidden
                        strokeWidth={2}
                      />
                      <span>Generating image…</span>
                    </div>
                  ) : null}

                  {gVideo?.kind === "loading" ? (
                    <div
                      className="flex items-center gap-2 text-[12px] text-cyan-100/75"
                      role="status"
                    >
                      <Loader2
                        className="h-4 w-4 animate-spin text-cyan-300/90"
                        aria-hidden
                        strokeWidth={2}
                      />
                      <span>
                        {gVideo.phase === "queued"
                          ? "Queued video generation…"
                          : "Generating video…"}
                      </span>
                    </div>
                  ) : null}

                  {gImage?.kind === "error" ? (
                    <div className="rounded-md border border-red-500/25 bg-red-950/35 px-2.5 py-2 text-[12px] text-red-100/90">
                      <p className="font-medium text-red-200/95">Image generation failed</p>
                      <p className="mt-1 text-[11px] leading-snug text-red-100/80">
                        {gImage.message}
                      </p>
                      {gImage.promptPreview ? (
                        <p className="mt-1 line-clamp-2 text-[10px] text-red-100/55">
                          Prompt: {gImage.promptPreview}
                        </p>
                      ) : null}
                    </div>
                  ) : null}

                  {gVideo?.kind === "error" ? (
                    <div className="rounded-md border border-red-500/25 bg-red-950/35 px-2.5 py-2 text-[12px] text-red-100/90">
                      <p className="font-medium text-red-200/95">Video generation failed</p>
                      <p className="mt-1 text-[11px] leading-snug text-red-100/80">
                        {gVideo.message}
                      </p>
                      {gVideo.promptPreview ? (
                        <p className="mt-1 line-clamp-2 text-[10px] text-red-100/55">
                          Prompt: {gVideo.promptPreview}
                        </p>
                      ) : null}
                    </div>
                  ) : null}

                  {gImage?.kind === "ready" ? (
                    <div className="space-y-2">
                      <div className="overflow-hidden rounded-lg border border-white/[0.1] bg-black/25">
                        <img
                          src={gImage.blobUrl}
                          alt={gImage.promptExcerpt || "Generated image"}
                          className="max-h-[min(52vh,28rem)] w-full object-contain"
                        />
                      </div>
                      {gImage.promptExcerpt ? (
                        <p className="line-clamp-2 text-[11px] leading-snug text-white/45">
                          {gImage.promptExcerpt}
                        </p>
                      ) : null}
                      {gImage.generatedFromReference ? (
                        <p className="text-[10px] leading-snug text-white/42">
                          Generated from reference image
                        </p>
                      ) : null}
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-white/38">
                        {gImage.modelId ? (
                          <span className="rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-white/55">
                            {gImage.modelId}
                          </span>
                        ) : null}
                        {gImage.providerLabel ? (
                          <span className="text-white/40">via {gImage.providerLabel}</span>
                        ) : null}
                        {typeof gImage.width === "number" && typeof gImage.height === "number"
                          ? `${gImage.width} × ${gImage.height}`
                          : null}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <a
                          href={gImage.blobUrl}
                          download={gImage.safeDisplayName || "generated-image.bin"}
                          className="inline-flex items-center gap-1 rounded-md border border-emerald-500/25 bg-emerald-950/35 px-2.5 py-1 text-[11px] font-medium text-emerald-100/95 hover:bg-emerald-950/55"
                        >
                          <ImageDown
                            className="h-3.5 w-3.5 opacity-95"
                            aria-hidden
                            strokeWidth={2}
                          />
                          Download
                        </a>
                        {canCopyImagePrompt ? (
                          <button
                            type="button"
                            className="inline-flex items-center gap-1 rounded-md border border-white/[0.1] px-2.5 py-1 text-[11px] font-medium text-white/70 hover:bg-white/[0.06]"
                            onClick={() => {
                              void copyToClipboard("Prompt", gImage.promptExcerpt);
                            }}
                          >
                            <Copy className="h-3.5 w-3.5 opacity-85" aria-hidden strokeWidth={2} />
                            Copy prompt
                          </button>
                        ) : null}
                        {onRemoveGeneratedImage ? (
                          <button
                            type="button"
                            className="inline-flex items-center gap-1 rounded-md border border-white/[0.08] px-2.5 py-1 text-[11px] font-medium text-white/55 hover:bg-red-950/40 hover:text-red-100/90"
                            onClick={() => {
                              onRemoveGeneratedImage(m.id);
                            }}
                          >
                            <Trash2
                              className="h-3.5 w-3.5 opacity-85"
                              aria-hidden
                              strokeWidth={2}
                            />
                            Remove
                          </button>
                        ) : null}
                      </div>
                    </div>
                  ) : null}

                  {gVideo?.kind === "ready" ? (
                    <div className="space-y-2">
                      <div className="overflow-hidden rounded-lg border border-white/[0.1] bg-black/25">
                        <video
                          controls
                          src={gVideo.blobUrl}
                          className="max-h-[min(52vh,28rem)] w-full object-contain"
                          aria-label={gVideo.promptExcerpt || "Generated video"}
                        />
                      </div>
                      {gVideo.promptExcerpt ? (
                        <p className="line-clamp-2 text-[11px] leading-snug text-white/45">
                          {gVideo.promptExcerpt}
                        </p>
                      ) : null}
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-white/38">
                        {gVideo.modelId ? (
                          <span className="rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-white/55">
                            {gVideo.modelId}
                          </span>
                        ) : null}
                        {gVideo.providerLabel ? (
                          <span className="text-white/40">via {gVideo.providerLabel}</span>
                        ) : null}
                        <span className="inline-flex items-center gap-1 text-white/45">
                          <Clapperboard className="h-3 w-3" aria-hidden strokeWidth={2} />
                          {gVideo.mimeType}
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <a
                          href={gVideo.blobUrl}
                          download={gVideo.safeDisplayName || "generated-video.bin"}
                          className="inline-flex items-center gap-1 rounded-md border border-cyan-500/25 bg-cyan-950/35 px-2.5 py-1 text-[11px] font-medium text-cyan-100/95 hover:bg-cyan-950/55"
                        >
                          <ImageDown
                            className="h-3.5 w-3.5 opacity-95"
                            aria-hidden
                            strokeWidth={2}
                          />
                          Download
                        </a>
                        {canCopyVideoPrompt ? (
                          <button
                            type="button"
                            className="inline-flex items-center gap-1 rounded-md border border-white/[0.1] px-2.5 py-1 text-[11px] font-medium text-white/70 hover:bg-white/[0.06]"
                            onClick={() => {
                              void copyToClipboard("Prompt", gVideo.promptExcerpt);
                            }}
                          >
                            <Copy className="h-3.5 w-3.5 opacity-85" aria-hidden strokeWidth={2} />
                            Copy prompt
                          </button>
                        ) : null}
                        {onRemoveGeneratedVideo ? (
                          <button
                            type="button"
                            className="inline-flex items-center gap-1 rounded-md border border-white/[0.08] px-2.5 py-1 text-[11px] font-medium text-white/55 hover:bg-red-950/40 hover:text-red-100/90"
                            onClick={() => {
                              onRemoveGeneratedVideo(m.id);
                            }}
                          >
                            <Trash2
                              className="h-3.5 w-3.5 opacity-85"
                              aria-hidden
                              strokeWidth={2}
                            />
                            Remove
                          </button>
                        ) : null}
                      </div>
                    </div>
                  ) : null}

                  {!thinkingHere && !gImage && !gVideo ? (
                    <>
                      <p className="whitespace-pre-wrap break-words">
                        {visibleContent || "\u00a0"}
                      </p>
                      {interrupted ? (
                        <p className="mt-2 text-[11px] text-amber-200/85">
                          Connection interrupted. Ask me to continue.
                        </p>
                      ) : null}
                    </>
                  ) : null}

                  {!thinkingHere &&
                  (gImage?.kind === "ready" || gVideo?.kind === "ready") &&
                  visibleContent.trim() ? (
                    <p className="mt-2 whitespace-pre-wrap break-words text-white/82">
                      {visibleContent}
                    </p>
                  ) : null}

                  <p className="mt-1.5 text-[10px] text-white/30">{m.timestamp}</p>
                </div>
                <div className="flex flex-wrap gap-1">
                  {canCopyAssistantPlain ? (
                    <IconTextButton
                      label="Copy"
                      icon={<Copy className="h-3 w-3 opacity-85" aria-hidden strokeWidth={2} />}
                      onClick={() => {
                        void copyToClipboard("Message", assistantTextToCopy);
                      }}
                    />
                  ) : null}
                  {gImage?.kind === "error" && gImage.message.trim() ? (
                    <IconTextButton
                      label="Copy error"
                      icon={<Copy className="h-3 w-3 opacity-85" aria-hidden strokeWidth={2} />}
                      onClick={() => {
                        void copyToClipboard("Error", gImage.message);
                      }}
                    />
                  ) : null}
                  {gVideo?.kind === "error" && gVideo.message.trim() ? (
                    <IconTextButton
                      label="Copy error"
                      icon={<Copy className="h-3 w-3 opacity-85" aria-hidden strokeWidth={2} />}
                      onClick={() => {
                        void copyToClipboard("Error", gVideo.message);
                      }}
                    />
                  ) : null}
                </div>
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
