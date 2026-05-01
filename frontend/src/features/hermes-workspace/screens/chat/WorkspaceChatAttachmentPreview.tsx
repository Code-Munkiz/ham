/**
 * Upstream `attachment-preview` + `AttachmentPreviewList` — chip/cards, removable, image thumb or file icon.
 * HAM dark theme; no @base-ui PreviewCard (not in this repo) — popover is optional detail via expand.
 */
import * as React from "react";
import { FileText, Loader2, RotateCcw, Video, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  type WorkspaceComposerAttachment,
  formatAttachmentByteSize,
} from "./composerAttachmentHelpers";

type WorkspaceChatAttachmentPreviewProps = {
  attachment: WorkspaceComposerAttachment;
  onRemove: (id: string) => void;
  onRetryUpload?: (id: string) => void;
};

function fileExt(name: string): string {
  const parts = name.split(".");
  return parts.length > 1 ? (parts.pop() ?? "").toUpperCase() : "FILE";
}

export function WorkspaceChatAttachmentPreview({
  attachment,
  onRemove,
  onRetryUpload,
}: WorkspaceChatAttachmentPreviewProps) {
  const hasError = Boolean(attachment.error);
  const uploading = attachment.uploadPhase === "uploading";
  const uploadFailed = attachment.uploadPhase === "failed";
  const canRetry = Boolean(uploadFailed && attachment.pendingSource && onRetryUpload);
  const showImg =
    !hasError &&
    attachment.kind === "image" &&
    (attachment.payload.startsWith("data:") || attachment.payload.startsWith("blob:"));

  return (
    <div
      className={cn(
        "relative flex max-w-[220px] items-center gap-1.5 rounded-md border p-1.5",
        hasError || uploadFailed
          ? "border-red-400/50 bg-red-950/40"
          : uploading
            ? "border-sky-500/35 bg-sky-950/25"
            : "border-white/[0.1] bg-white/[0.05]",
      )}
    >
      <div className="relative h-7 w-7 shrink-0 overflow-hidden rounded bg-white/[0.07]">
        {uploading ? (
          <div className="flex h-full w-full items-center justify-center text-sky-200/85">
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden strokeWidth={2} />
          </div>
        ) : showImg ? (
          <img
            src={attachment.payload}
            alt=""
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-white/50">
            {attachment.kind === "video" ? (
              <Video className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden />
            ) : (
              <FileText className="h-3.5 w-3.5" strokeWidth={1.5} />
            )}
          </div>
        )}
      </div>
      <div className="min-w-0 flex-1 text-left">
        <p className="line-clamp-1 text-[10px] font-medium text-white/90">{attachment.name}</p>
        {uploading ? (
          <p className="text-[9px] text-sky-200/75">Uploading…</p>
        ) : hasError || uploadFailed ? (
          <p className="line-clamp-2 text-[9px] text-red-300/90">{attachment.error}</p>
        ) : (
          <p className="text-[9px] text-white/40">
            {attachment.kind === "video"
              ? `Video attached — processing not enabled yet · ${formatAttachmentByteSize(attachment.size)}`
              : `${fileExt(attachment.name)} • ${formatAttachmentByteSize(attachment.size)}`}
          </p>
        )}
      </div>
      {canRetry ? (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-5 w-5 shrink-0 rounded-full p-0 text-sky-300/85 hover:bg-sky-500/15 hover:text-sky-100"
          onClick={() => onRetryUpload?.(attachment.id)}
          aria-label="Retry upload"
          title="Retry upload"
        >
          <RotateCcw className="h-3 w-3" strokeWidth={1.75} />
        </Button>
      ) : null}
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-5 w-5 shrink-0 rounded-full p-0 text-white/40 hover:bg-white/10 hover:text-white/90"
        onClick={() => onRemove(attachment.id)}
        aria-label="Remove attachment"
      >
        <X className="h-3 w-3" strokeWidth={1.5} />
      </Button>
    </div>
  );
}

type WorkspaceChatAttachmentPreviewListProps = {
  attachments: WorkspaceComposerAttachment[];
  onRemove: (id: string) => void;
  onRetryUpload?: (id: string) => void;
  className?: string;
};

export function WorkspaceChatAttachmentPreviewList({
  attachments,
  onRemove,
  onRetryUpload,
  className,
}: WorkspaceChatAttachmentPreviewListProps) {
  if (attachments.length === 0) return null;
  return (
    <div className={cn("mb-2 flex w-full max-w-[56rem] flex-wrap items-start gap-1.5 md:pl-1", className)}>
      {attachments.map((a) => (
        <WorkspaceChatAttachmentPreview
          key={a.id}
          attachment={a}
          onRemove={onRemove}
          onRetryUpload={onRetryUpload}
        />
      ))}
    </div>
  );
}
