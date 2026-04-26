/**
 * Upstream `attachment-preview` + `AttachmentPreviewList` — chip/cards, removable, image thumb or file icon.
 * HAM dark theme; no @base-ui PreviewCard (not in this repo) — popover is optional detail via expand.
 */
import * as React from "react";
import { FileText, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  type WorkspaceComposerAttachment,
  formatAttachmentByteSize,
} from "./composerAttachmentHelpers";

type WorkspaceChatAttachmentPreviewProps = {
  attachment: WorkspaceComposerAttachment;
  onRemove: (id: string) => void;
};

function fileExt(name: string): string {
  const parts = name.split(".");
  return parts.length > 1 ? (parts.pop() ?? "").toUpperCase() : "FILE";
}

export function WorkspaceChatAttachmentPreview({ attachment, onRemove }: WorkspaceChatAttachmentPreviewProps) {
  const hasError = Boolean(attachment.error);
  const showImg = !hasError && attachment.kind === "image" && attachment.payload.startsWith("data:");

  return (
    <div
      className={cn(
        "relative flex max-w-[220px] items-center gap-1.5 rounded-md border p-1.5",
        hasError
          ? "border-red-400/50 bg-red-950/40"
          : "border-white/[0.1] bg-white/[0.05]",
      )}
    >
      <div className="relative h-7 w-7 shrink-0 overflow-hidden rounded bg-white/[0.07]">
        {showImg ? (
          <img
            src={attachment.payload}
            alt=""
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-white/50">
            <FileText className="h-3.5 w-3.5" strokeWidth={1.5} />
          </div>
        )}
      </div>
      <div className="min-w-0 flex-1 text-left">
        <p className="line-clamp-1 text-[10px] font-medium text-white/90">{attachment.name}</p>
        {hasError ? (
          <p className="line-clamp-2 text-[9px] text-red-300/90">{attachment.error}</p>
        ) : (
          <p className="text-[9px] text-white/40">
            {fileExt(attachment.name)} • {formatAttachmentByteSize(attachment.size)}
          </p>
        )}
      </div>
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
  className?: string;
};

export function WorkspaceChatAttachmentPreviewList({ attachments, onRemove, className }: WorkspaceChatAttachmentPreviewListProps) {
  if (attachments.length === 0) return null;
  return (
    <div className={cn("mb-2 flex w-full max-w-[56rem] flex-wrap items-start gap-1.5 md:pl-1", className)}>
      {attachments.map((a) => (
        <WorkspaceChatAttachmentPreview key={a.id} attachment={a} onRemove={onRemove} />
      ))}
    </div>
  );
}
