/**
 * Upstream-style composer: attach | mic | input | send — HAM stream only; attachments inlined per `composerAttachmentHelpers`.
 */

import * as React from "react";
import { ArrowUp, Paperclip } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ModelCatalogItem, ModelCatalogPayload } from "@/lib/ham/types";
import { isDashboardChatGatewayReady } from "@/lib/ham/types";
import { VoiceMessageInput } from "@/components/chat/VoiceMessageInput";
import {
  type WorkspaceComposerAttachment,
  formatAttachmentByteSize,
  WORKSPACE_ATTACHMENT_ACCEPT,
} from "./composerAttachmentHelpers";

type WorkspaceChatComposerProps = {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  sending: boolean;
  voiceTranscribing: boolean;
  onVoiceBlob: (blob: Blob) => void;
  attachment: WorkspaceComposerAttachment | null;
  onAttachmentClear: () => void;
  onAttachmentFile: (file: File) => void;
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
  attachment,
  onAttachmentClear,
  onAttachmentFile,
  catalog,
  modelId,
  onModelIdChange,
}: WorkspaceChatComposerProps) {
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const formRef = React.useRef<HTMLFormElement>(null);
  const showModel = catalog && catalog.gateway_mode === "openrouter" && chatModelCandidates(catalog).length > 0;
  const gatewayOk = isDashboardChatGatewayReady(catalog);
  const canSend = gatewayOk && (value.trim() || attachment) && !sending && !voiceTranscribing;

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
      {attachment ? (
        <div className="mb-2 flex w-full max-w-[56rem] items-center justify-between gap-2 rounded-lg border border-white/[0.08] bg-white/[0.04] px-2.5 py-2 md:pl-1">
          <p className="min-w-0 truncate text-[11px] text-white/80">
            <span className="text-white/45">Attached: </span>
            {attachment.name}{" "}
            <span className="text-white/35">({formatAttachmentByteSize(attachment.size)})</span>
          </p>
          <button
            type="button"
            onClick={onAttachmentClear}
            className="shrink-0 text-[11px] text-[#7dd3fc] underline decoration-white/10 underline-offset-2 hover:decoration-[#7dd3fc]/50"
          >
            Remove
          </button>
        </div>
      ) : null}
      <form
        ref={formRef}
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
        className="w-full max-w-[56rem] md:pl-1"
      >
        <input
          ref={fileInputRef}
          type="file"
          className="sr-only"
          accept={WORKSPACE_ATTACHMENT_ACCEPT}
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) onAttachmentFile(f);
          }}
        />
        <div
          className={cn(
            "flex items-end gap-1.5 rounded-2xl border border-white/[0.1] bg-[#050c14]/95 p-1.5 shadow-lg md:gap-2",
            "ring-0 focus-within:border-[#c45c12]/40 focus-within:shadow-[0_0_0_1px_rgba(196,92,18,0.2)]",
          )}
        >
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-10 w-9 shrink-0 text-white/45 hover:bg-white/[0.06] hover:text-white/85"
            disabled={sending || voiceTranscribing}
            onClick={() => fileInputRef.current?.click()}
            aria-label="Attach file"
            title="Attach a file — text and images are inlined into your message (max 500 KB)."
          >
            <Paperclip className="h-4 w-4" strokeWidth={1.5} />
          </Button>

          <div
            className="flex shrink-0 items-center"
            title={
              voiceTranscribing
                ? "Transcribing…"
                : "Voice — record and transcribe into the message (HAM /api/chat/transcribe)"
            }
          >
            <VoiceMessageInput
              compact
              hidePreview
              disabled={sending || voiceTranscribing || disabled}
              onVoiceMessage={(blob) => {
                onVoiceBlob(blob);
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
                  : "Message Hermes…"
            }
            className="hww-input max-h-40 min-h-[44px] min-w-0 flex-1 resize-none border-0 bg-transparent px-1 py-2.5 text-[13px] text-[#e8eef3] placeholder:text-white/30 focus:ring-0"
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
      </form>
    </div>
  );
}
