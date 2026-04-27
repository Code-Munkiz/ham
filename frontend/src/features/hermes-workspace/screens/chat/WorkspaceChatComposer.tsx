/**
 * Hermes Workspace chat: repomix-style PromptInput shell — preview strip, prompt row, then action toolbar
 * (attach | voice | token/model | send). v2 attachment uploads go through `POST /api/chat/attachments`.
 */

import * as React from "react";
import { ArrowUp, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ModelCatalogItem, ModelCatalogPayload } from "@/lib/ham/types";
import { isDashboardChatGatewayReady } from "@/lib/ham/types";
import { WorkspaceVoiceMessageInput } from "./WorkspaceVoiceMessageInput";
import { toast } from "sonner";
import { WorkspaceChatAttachmentButton } from "./WorkspaceChatAttachmentButton";
import { WorkspaceChatAttachmentPreviewList } from "./WorkspaceChatAttachmentPreview";
import {
  type WorkspaceComposerAttachment,
  MAX_WORKSPACE_ATTACHMENT_COUNT,
} from "./composerAttachmentHelpers";

type WorkspaceChatComposerProps = {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  sending: boolean;
  voiceTranscribing: boolean;
  onVoiceBlob: (blob: Blob) => void;
  attachments: WorkspaceComposerAttachment[];
  onAddAttachments: (files: File[]) => void;
  onRemoveAttachment: (id: string) => void;
  catalog: ModelCatalogPayload | null;
  modelId: string | null;
  onModelIdChange: (id: string | null) => void;
};

function chatModelCandidates(c: ModelCatalogPayload | null): ModelCatalogItem[] {
  if (!c?.items?.length) return [];
  return c.items.filter((x) => x.supports_chat);
}

export function WorkspaceChatComposer({
  value,
  onChange,
  onSubmit,
  disabled,
  sending,
  voiceTranscribing,
  onVoiceBlob,
  attachments,
  onAddAttachments,
  onRemoveAttachment,
  catalog,
  modelId,
  onModelIdChange,
}: WorkspaceChatComposerProps) {
  const [voiceRecording, setVoiceRecording] = React.useState(false);
  const [voiceBanner, setVoiceBanner] = React.useState<string | null>(null);
  const [isDragging, setIsDragging] = React.useState(false);
  const formRef = React.useRef<HTMLFormElement>(null);
  const outerRef = React.useRef<HTMLDivElement>(null);
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const dragDepthRef = React.useRef(0);
  const TEXTAREA_MAX_PX = 240;

  const syncTextareaHeight = React.useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const sh = el.scrollHeight;
    const h = Math.min(sh, TEXTAREA_MAX_PX);
    el.style.height = `${h}px`;
    el.style.overflowY = sh > TEXTAREA_MAX_PX ? "auto" : "hidden";
  }, [TEXTAREA_MAX_PX]);

  React.useLayoutEffect(() => {
    syncTextareaHeight();
  }, [value, syncTextareaHeight]);

  React.useLayoutEffect(() => {
    const el = outerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const h = el.offsetHeight;
      if (h > 0) {
        document.documentElement.style.setProperty("--hww-chat-composer-height", `${h}px`);
      }
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
    };
  }, [attachments.length, voiceRecording, voiceTranscribing, value]);

  React.useEffect(() => {
    if (voiceRecording) setVoiceBanner(null);
  }, [voiceRecording]);
  const showModel =
    Boolean(catalog && catalog.gateway_mode === "openrouter" && chatModelCandidates(catalog).length > 0);
  const gatewayOk = isDashboardChatGatewayReady(catalog);
  const hasAttachErrOnly =
    attachments.length > 0 && attachments.every((a) => a.error) && !value.trim();
  const allAttachmentsFailed = attachments.length > 0 && attachments.every((a) => a.error);
  const canSend =
    gatewayOk &&
    !allAttachmentsFailed &&
    (value.trim() || (attachments.length > 0 && !hasAttachErrOnly)) &&
    !sending &&
    !voiceTranscribing &&
    !voiceRecording;

  const handleAddFiles = React.useCallback(
    (files: File[]) => {
      if (attachments.length >= MAX_WORKSPACE_ATTACHMENT_COUNT) {
        toast.error(`Up to ${MAX_WORKSPACE_ATTACHMENT_COUNT} attachments.`);
        return;
      }
      const remaining = Math.max(0, MAX_WORKSPACE_ATTACHMENT_COUNT - attachments.length);
      const slice = files.slice(0, remaining);
      if (files.length > remaining) {
        toast.error(`Up to ${MAX_WORKSPACE_ATTACHMENT_COUNT} attachments.`);
      }
      onAddAttachments(slice);
    },
    [attachments.length, onAddAttachments],
  );

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragDepthRef.current = 0;
    setIsDragging(false);
    if (disabled || sending || voiceTranscribing || voiceRecording) return;
    const dt = e.dataTransfer?.files;
    if (!dt?.length) return;
    handleAddFiles(Array.from(dt));
  };

  const onDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (disabled || sending || voiceTranscribing || voiceRecording) return;
    dragDepthRef.current += 1;
    if (dragDepthRef.current === 1) setIsDragging(true);
  };

  const onDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) setIsDragging(false);
  };

  return (
    <div
      ref={outerRef}
      className="hww-chat-composer-outer pointer-events-auto w-full max-w-[40rem] shrink-0 border-t border-white/[0.06] bg-[#030a10]/90 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur-sm md:px-4"
    >
      <form
        ref={formRef}
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
        className="w-full md:pl-1"
      >
        <div
          className={cn(
            "relative flex min-w-0 flex-col overflow-hidden rounded-3xl border border-white/[0.1] bg-[#050c14]/95",
            "shadow-[0_0_0_1px_rgba(255,255,255,0.03)]",
            "ring-0 focus-within:border-[#c45c12]/40 focus-within:shadow-[0_0_0_1px_rgba(196,92,18,0.2)]",
            isDragging && "border-[#c45c12]/50 ring-2 ring-[#c45c12]/20",
          )}
          onDragEnter={onDragEnter}
          onDragLeave={onDragLeave}
          onDragOver={onDragOver}
          onDrop={onDrop}
        >
          {isDragging ? (
            <div
              className="pointer-events-none absolute inset-1 z-20 flex items-center justify-center rounded-[1.1rem] border-2 border-dashed border-[#c45c12]/50 bg-[#030a10]/80 text-[12px] font-medium text-[#ffb27a] backdrop-blur-sm"
              aria-hidden
            >
              Drop files to attach
            </div>
          ) : null}

          {attachments.length > 0 ? (
            <div className="border-b border-white/[0.06] px-2 pb-1.5 pt-2 md:px-3">
              <WorkspaceChatAttachmentPreviewList
                className="mb-0"
                attachments={attachments}
                onRemove={onRemoveAttachment}
              />
            </div>
          ) : null}

          {voiceBanner ? (
            <div
              className="flex items-start gap-2 border-b border-red-500/25 bg-red-950/35 px-3 py-2 text-[11px] leading-snug text-red-100/90"
              role="alert"
            >
              <span className="min-w-0 flex-1">{voiceBanner}</span>
              <button
                type="button"
                className="shrink-0 rounded-md px-1.5 py-0.5 text-[13px] leading-none text-red-200/90 hover:bg-white/10"
                aria-label="Dismiss voice message"
                onClick={() => setVoiceBanner(null)}
              >
                ×
              </button>
            </div>
          ) : null}
          {(voiceRecording || voiceTranscribing) && (
            <div
              className="flex items-center gap-1.5 border-b border-white/[0.05] px-3 py-1.5 text-[10px] font-medium uppercase tracking-wide"
              role="status"
            >
              {voiceTranscribing ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-[#7dd3fc]" />
                  <span className="text-[#7dd3fc]">Transcribing…</span>
                </>
              ) : (
                <>
                  <span className="inline-flex h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-red-500" />
                  <span className="text-red-200/90">Recording — stop the mic to finish</span>
                </>
              )}
            </div>
          )}

          <div className="px-2 pt-1 md:px-3 md:pt-1.5">
            <label htmlFor="hww-chat-composer" className="sr-only">
              Message
            </label>
            <textarea
              ref={textareaRef}
              id="hww-chat-composer"
              value={value}
              onChange={(e) => onChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  if (canSend) onSubmit();
                }
              }}
              rows={1}
              disabled={disabled || sending || voiceTranscribing}
              placeholder={
                voiceTranscribing
                  ? "Transcribing…"
                  : !gatewayOk && catalog && !sending
                    ? "Chat gateway not ready — check /api/models"
                    : "Ask anything… (Enter to send, Shift+Enter for newline)"
              }
              className="w-full min-h-[44px] max-h-[240px] resize-none border-0 bg-transparent px-1 py-2 text-[13px] leading-[1.35] text-[#e8eef3] outline-none placeholder:text-white/35 focus:ring-0 focus:outline-none [box-shadow:none] overflow-x-hidden"
            />
          </div>

          <div className="flex min-h-[48px] items-center justify-between gap-1 border-t border-white/[0.06] px-1.5 py-1.5 md:gap-2 md:px-2.5 md:py-2">
            <div className="flex shrink-0 items-center gap-0.5 md:gap-1">
              <WorkspaceChatAttachmentButton
                onFiles={handleAddFiles}
                disabled={sending || voiceTranscribing || voiceRecording || disabled}
              />
              <div
                className={cn(
                  "flex shrink-0 items-center",
                  voiceTranscribing && "pointer-events-none opacity-40",
                )}
                title="Voice — record, then HAM transcribes into the field"
              >
                <WorkspaceVoiceMessageInput
                  compact
                  hidePreview
                  disabled={sending || voiceTranscribing || disabled}
                  onRecordingChange={setVoiceRecording}
                  onVoiceRecorderErrorChange={setVoiceBanner}
                  onVoiceError={(err) => {
                    setVoiceBanner(err);
                  }}
                  onVoiceMessage={(blob) => {
                    void onVoiceBlob(blob);
                  }}
                />
              </div>
            </div>

            <div className="flex min-w-0 flex-1 items-center justify-end gap-1.5 md:gap-2">
              {value.length >= 100 ? (
                <span
                  className="hidden min-w-0 text-[10px] tabular-nums text-white/30 select-none sm:inline"
                  title="Approximate token count"
                >
                  ~{Math.ceil(value.length / 4)} tokens
                </span>
              ) : null}
              {showModel ? (
                <select
                  id="hww-chat-model"
                  className="hww-input max-w-[9rem] shrink truncate rounded-md py-1 text-[11px] md:max-w-[14rem] md:py-1.5 md:text-[12px]"
                  value={modelId ?? ""}
                  onChange={(e) => onModelIdChange(e.target.value ? e.target.value : null)}
                  disabled={sending}
                  aria-label="Model"
                >
                  {chatModelCandidates(catalog!).map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label || m.id}
                    </option>
                  ))}
                </select>
              ) : null}
            </div>

            <Button
              type="submit"
              size="icon"
              disabled={!canSend}
              className="h-10 w-10 shrink-0 rounded-full bg-gradient-to-b from-[#c45c12] to-[#8f3d0a] text-white shadow-md hover:from-[#d66a18] hover:to-[#a44a0c] disabled:opacity-40"
              aria-label="Send"
            >
              {sending ? (
                <span className="h-4 w-4 animate-pulse rounded-full bg-white/80" />
              ) : (
                <ArrowUp className="h-4 w-4" strokeWidth={2.2} />
              )}
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
}
