/**
 * Hermes Workspace chat composer: PromptInput-style shell + action row (attach | mic | input | send).
 * Stream contract unchanged — attachments via `buildOutboundMessageWithAttachments`.
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
  const formRef = React.useRef<HTMLFormElement>(null);
  const showModel = catalog && catalog.gateway_mode === "openrouter" && chatModelCandidates(catalog).length > 0;
  const gatewayOk = isDashboardChatGatewayReady(catalog);
  const hasAttachErrOnly =
    attachments.length > 0 && attachments.every((a) => a.error) && !value.trim();
  const canSend =
    gatewayOk &&
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

  return (
    <div
      className="hww-chat-composer-outer pointer-events-auto shrink-0 border-t border-white/[0.06] bg-[#030a10]/90 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur-sm md:px-4"
    >
      {showModel ? (
        <div className="mb-2 flex w-full max-w-[56rem] flex-wrap items-center gap-2 md:pl-1">
          <label htmlFor="hww-chat-model" className="text-[10px] font-medium uppercase tracking-wide text-white/35">
            Model
          </label>
          <select
            id="hww-chat-model"
            className="hww-input max-w-md flex-1 rounded-md py-1.5 text-[12px]"
            value={modelId ?? ""}
            onChange={(e) => onModelIdChange(e.target.value ? e.target.value : null)}
            disabled={sending}
          >
            {chatModelCandidates(catalog!).map((m) => (
              <option key={m.id} value={m.id}>
                {m.label || m.id}
              </option>
            ))}
          </select>
        </div>
      ) : null}

      <WorkspaceChatAttachmentPreviewList attachments={attachments} onRemove={onRemoveAttachment} />

      <form
        ref={formRef}
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
        className="w-full max-w-[56rem] md:pl-1"
      >
        <div
          className={cn(
            "flex flex-col overflow-hidden rounded-3xl border border-white/[0.1] bg-[#050c14]/95 shadow-[0_0_0_1px_rgba(255,255,255,0.03)]",
            "ring-0 focus-within:border-[#c45c12]/40 focus-within:shadow-[0_0_0_1px_rgba(196,92,18,0.2)]",
          )}
        >
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

          <div className="flex items-end gap-1 px-1.5 py-1.5 md:gap-2">
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
                onVoiceError={(err) => {
                  toast.error(err, { duration: 5000 });
                }}
                onVoiceMessage={(blob) => {
                  void onVoiceBlob(blob);
                }}
              />
            </div>

            <label htmlFor="hww-chat-composer" className="sr-only">
              Message
            </label>
            <textarea
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
              className="hww-input min-h-[44px] w-full min-w-0 max-h-40 flex-1 resize-none border-0 bg-transparent px-1 py-2.5 text-[13px] text-[#e8eef3] placeholder:text-white/30 focus:ring-0"
            />
            <Button
              type="submit"
              size="icon"
              disabled={!canSend}
              className="h-10 w-10 shrink-0 rounded-xl bg-gradient-to-b from-[#c45c12] to-[#8f3d0a] text-white hover:from-[#d66a18] hover:to-[#a44a0c] disabled:opacity-40"
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
