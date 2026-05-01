/**
 * Composer "+" opens a small action menu: attach (existing hidden file input) + Export PDF entry.
 */
import * as React from "react";
import { ChevronRight, FileDown, Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { WORKSPACE_ATTACHMENT_ACCEPT } from "./composerAttachmentHelpers";

export type ComposerExportPdfState = {
  onExport: () => void;
  busy: boolean;
  /** When non-null, Export PDF row stays visible but is not clickable. */
  blockedReason: "none" | "no_session" | "no_transcript" | "streaming" | "session_error";
};

function exportBlockedMessage(reason: ComposerExportPdfState["blockedReason"]): string {
  switch (reason) {
    case "no_session":
      return "Start a chat first";
    case "no_transcript":
      return "Add a message first";
    case "streaming":
      return "Wait for response to finish";
    case "session_error":
      return "Session unavailable";
    default:
      return "";
  }
}

type WorkspaceChatComposerActionsMenuProps = {
  onFiles: (files: File[]) => void;
  attachDisabled: boolean;
  exportPdf: ComposerExportPdfState;
  /** Shown under menu rows / in title attributes — honest capability copy. */
  attachFooterNote?: string;
  className?: string;
};

export function WorkspaceChatComposerActionsMenu({
  onFiles,
  attachDisabled,
  exportPdf,
  attachFooterNote,
  className,
}: WorkspaceChatComposerActionsMenuProps) {
  const [open, setOpen] = React.useState(false);
  const wrapRef = React.useRef<HTMLDivElement>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      const el = wrapRef.current;
      if (!el || el.contains(e.target as Node)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDoc, true);
    return () => document.removeEventListener("mousedown", onDoc, true);
  }, [open]);

  const exportBlocked = exportPdf.blockedReason !== "none" || exportPdf.busy;
  const exportHint = exportPdf.busy
    ? "Generating PDF…"
    : exportBlocked
      ? exportBlockedMessage(exportPdf.blockedReason)
      : "Download this chat transcript";

  return (
    <div className={cn("relative shrink-0", className)} ref={wrapRef}>
      <input
        ref={inputRef}
        type="file"
        className="sr-only"
        accept={WORKSPACE_ATTACHMENT_ACCEPT}
        multiple
        aria-hidden
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";
          if (files.length) onFiles(files);
          setOpen(false);
        }}
      />
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className={cn(
          "h-10 w-10 shrink-0 rounded-lg text-white/55 hover:bg-white/[0.08] hover:text-[#7dd3fc]",
          open && "bg-white/[0.08] text-[#7dd3fc]",
        )}
        onClick={() => setOpen((o) => !o)}
        aria-label="Composer actions"
        aria-expanded={open}
        aria-haspopup="menu"
        title="Add files or export PDF"
      >
        <Plus className="h-5 w-5" strokeWidth={1.5} />
      </Button>
      {open ? (
        <div
          className="absolute bottom-full left-0 z-[60] mb-1.5 min-w-[min(92vw,17.5rem)] rounded-xl border border-white/[0.12] bg-[#050f0c]/98 py-1 shadow-[0_12px_40px_rgba(0,0,0,0.45)] backdrop-blur-md"
          role="menu"
          aria-label="Composer actions"
        >
          <button
            type="button"
            role="menuitem"
            disabled={attachDisabled}
            className={cn(
              "flex w-full flex-col items-start gap-0.5 px-3 py-2.5 text-left text-[12px] transition-colors",
              attachDisabled
                ? "cursor-not-allowed text-white/35"
                : "text-white/88 hover:bg-white/[0.07]",
            )}
            onClick={() => {
              if (attachDisabled) return;
              inputRef.current?.click();
            }}
          >
            <span className="flex w-full items-center justify-between gap-2 font-medium">
              Add photos &amp; files
              <ChevronRight className="h-3.5 w-3.5 shrink-0 opacity-45" aria-hidden />
            </span>
            <span className="text-[10px] font-normal leading-snug text-white/45">
              Upload images or documents
            </span>
            {attachFooterNote ? (
              <span className="text-[10px] font-normal leading-snug text-white/38">{attachFooterNote}</span>
            ) : null}
          </button>
          <div className="mx-2 h-px bg-white/[0.08]" role="separator" />
          <button
            type="button"
            role="menuitem"
            disabled={exportBlocked}
            className={cn(
              "flex w-full flex-col items-start gap-0.5 px-3 py-2.5 text-left text-[12px] transition-colors",
              exportBlocked
                ? "cursor-not-allowed text-white/40"
                : "text-white/88 hover:bg-white/[0.07]",
            )}
            title={exportHint}
            onClick={() => {
              if (exportBlocked) return;
              exportPdf.onExport();
              setOpen(false);
            }}
          >
            <span className="flex w-full items-center justify-between gap-2 font-medium">
              <span className="inline-flex items-center gap-1.5">
                {exportPdf.busy ? (
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-emerald-300/90" aria-hidden />
                ) : (
                  <FileDown className="h-3.5 w-3.5 shrink-0 opacity-80" aria-hidden />
                )}
                Export PDF
              </span>
            </span>
            <span className="text-[10px] font-normal leading-snug text-white/45">{exportHint}</span>
          </button>
        </div>
      ) : null}
    </div>
  );
}
