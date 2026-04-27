/**
 * Upstream `attachment-button` — attach affordance: Plus icon, rounded ghost (Hermes repomix), multi-select.
 * No Hugeicons dep; uses HAM shadcn Button.
 */
import * as React from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { WORKSPACE_ATTACHMENT_ACCEPT } from "./composerAttachmentHelpers";

type WorkspaceChatAttachmentButtonProps = {
  onFiles: (files: File[]) => void;
  disabled?: boolean;
  className?: string;
  /** "Attach images and documents" */
  "aria-label"?: string;
};

export function WorkspaceChatAttachmentButton({
  onFiles,
  disabled = false,
  className,
  "aria-label": ariaLabel = "Attach files",
}: WorkspaceChatAttachmentButtonProps) {
  const inputRef = React.useRef<HTMLInputElement>(null);

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        className="sr-only"
        accept={WORKSPACE_ATTACHMENT_ACCEPT}
        multiple
        aria-hidden
        onChange={(e) => {
          const list = e.target.files;
          e.target.value = "";
          if (!list?.length) return;
          onFiles(Array.from(list));
        }}
      />
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className={cn(
          "h-10 w-10 shrink-0 rounded-lg text-white/55 hover:bg-white/[0.08] hover:text-[#7dd3fc]",
          className,
        )}
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        aria-label={ariaLabel}
        title="Add attachments — text and images are inlined into the message (max 500 KB each, up to 8 files)."
      >
        <Plus className="h-5 w-5" strokeWidth={1.5} />
      </Button>
    </>
  );
}
