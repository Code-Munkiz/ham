/**
 * Composer "+" opens a small action menu: attach (existing hidden file input) + Export PDF entry.
 *
 * The menu is portaled to `document.body` with fixed positioning so it is not clipped by the
 * composer card's `overflow-hidden` (which would hide the upper rows when opening upward).
 */
import * as React from "react";
import { createPortal } from "react-dom";
import { ChevronRight, Clapperboard, FileDown, ImagePlus, Loader2, Plus } from "lucide-react";
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
      return "Nothing to export yet";
    case "streaming":
      return "Wait for reply";
    case "session_error":
      return "Session unavailable";
    default:
      return "";
  }
}

export type ComposerGenerateImageState = {
  onGenerate: () => void;
  busy: boolean;
  disabled: boolean;
  /** Short subtitle under the row label (capability / lock reason). */
  subtitle: string;
};

export type ComposerGenerateVideoState = {
  onGenerate: () => void;
  busy: boolean;
  disabled: boolean;
  subtitle: string;
};

type WorkspaceChatComposerActionsMenuProps = {
  onFiles: (files: File[]) => void;
  attachDisabled: boolean;
  /** Short line when attach row is disabled (e.g. uploads in progress). */
  attachDisabledReason?: string | null;
  /** Long capability honesty — tooltip on the Add files row (not inline). */
  attachDetailsTitle?: string | null;
  /** Optional one-line footer under menu actions. */
  menuFooterHint?: string | null;
  generateImage: ComposerGenerateImageState;
  generateVideo: ComposerGenerateVideoState;
  exportPdf: ComposerExportPdfState;
  className?: string;
};

export function WorkspaceChatComposerActionsMenu({
  onFiles,
  attachDisabled,
  attachDisabledReason = null,
  attachDetailsTitle = null,
  menuFooterHint = null,
  generateImage,
  generateVideo,
  exportPdf,
  className,
}: WorkspaceChatComposerActionsMenuProps) {
  const [open, setOpen] = React.useState(false);
  const [anchorRect, setAnchorRect] = React.useState<DOMRect | null>(null);
  const wrapRef = React.useRef<HTMLDivElement>(null);
  const menuPanelRef = React.useRef<HTMLDivElement>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const syncAnchorRect = React.useCallback(() => {
    const el = wrapRef.current;
    if (!el) return;
    setAnchorRect(el.getBoundingClientRect());
  }, []);

  React.useLayoutEffect(() => {
    if (!open) return;
    syncAnchorRect();
    const onScrollResize = () => syncAnchorRect();
    window.addEventListener("scroll", onScrollResize, true);
    window.addEventListener("resize", onScrollResize);
    return () => {
      window.removeEventListener("scroll", onScrollResize, true);
      window.removeEventListener("resize", onScrollResize);
    };
  }, [open, syncAnchorRect]);

  React.useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node;
      if (wrapRef.current?.contains(t) || menuPanelRef.current?.contains(t)) return;
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
      : "Download transcript";

  const generateBlocked = generateImage.disabled || generateImage.busy;
  const generateVideoBlocked = generateVideo.disabled || generateVideo.busy;

  const addFilesTitle =
    attachDisabled && attachDisabledReason?.trim()
      ? attachDisabledReason.trim()
      : attachDetailsTitle?.trim() ||
        "Documents and spreadsheets: text-extracted server-side. PDF export downloads the transcript only.";

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
        aria-label="Attachments, image generation, and export"
        aria-expanded={open}
        aria-haspopup="menu"
        title="Add files, generate image/video, or export PDF"
      >
        <Plus className="h-5 w-5" strokeWidth={1.5} />
      </Button>
      {open && anchorRect && typeof document !== "undefined"
        ? createPortal(
            <div
              ref={menuPanelRef}
              className="fixed z-[200] w-[min(92vw,13.75rem)] rounded-lg border border-white/[0.1] bg-[#050a0e]/95 py-0.5 shadow-[0_10px_32px_rgba(0,0,0,0.42)] backdrop-blur-md"
              style={{
                left: Math.max(8, anchorRect.left),
                bottom: window.innerHeight - anchorRect.top + 6,
              }}
              role="menu"
              aria-label="Composer actions"
            >
              <button
                type="button"
                role="menuitem"
                disabled={attachDisabled}
                title={addFilesTitle}
                className={cn(
                  "flex w-full flex-col gap-0 px-2.5 py-2 text-left text-[11px] transition-colors",
                  attachDisabled
                    ? "cursor-not-allowed opacity-50"
                    : "text-white/90 hover:bg-white/[0.06]",
                )}
                onClick={() => {
                  if (attachDisabled) return;
                  setOpen(false);
                  window.setTimeout(() => {
                    inputRef.current?.click();
                  }, 0);
                }}
              >
                <span className="flex w-full items-center justify-between gap-1.5 font-medium leading-tight text-white/92">
                  Add files
                  <ChevronRight
                    className="h-3 w-3 shrink-0 opacity-40"
                    aria-hidden
                    strokeWidth={2}
                  />
                </span>
                <span className="text-[10px] font-normal leading-snug text-white/42">
                  {attachDisabled
                    ? (attachDisabledReason ?? "Unavailable")
                    : "Images, docs, spreadsheets, MP4/MOV/WebM"}
                </span>
              </button>
              <div className="mx-2 my-0.5 h-px bg-white/[0.07]" role="separator" />
              <button
                type="button"
                role="menuitem"
                disabled={generateVideoBlocked}
                title={generateVideo.subtitle}
                className={cn(
                  "flex w-full flex-col gap-0 px-2.5 py-2 text-left text-[11px] transition-colors",
                  generateVideoBlocked
                    ? "cursor-not-allowed opacity-50"
                    : "text-white/90 hover:bg-white/[0.06]",
                )}
                onClick={() => {
                  if (generateVideoBlocked) return;
                  generateVideo.onGenerate();
                  setOpen(false);
                }}
              >
                <span className="flex w-full items-center gap-1.5 font-medium leading-tight text-white/92">
                  {generateVideo.busy ? (
                    <Loader2
                      className="h-3 w-3 shrink-0 animate-spin text-emerald-300/90"
                      aria-hidden
                    />
                  ) : (
                    <Clapperboard
                      className="h-3 w-3 shrink-0 opacity-75"
                      aria-hidden
                      strokeWidth={2}
                    />
                  )}
                  Generate video
                </span>
                <span className="text-[10px] font-normal leading-snug text-white/42">
                  {generateVideo.busy ? "Generating…" : generateVideo.subtitle}
                </span>
              </button>
              <div className="mx-2 my-0.5 h-px bg-white/[0.07]" role="separator" />
              <button
                type="button"
                role="menuitem"
                disabled={generateBlocked}
                title={generateImage.subtitle}
                className={cn(
                  "flex w-full flex-col gap-0 px-2.5 py-2 text-left text-[11px] transition-colors",
                  generateBlocked
                    ? "cursor-not-allowed opacity-50"
                    : "text-white/90 hover:bg-white/[0.06]",
                )}
                onClick={() => {
                  if (generateBlocked) return;
                  generateImage.onGenerate();
                  setOpen(false);
                }}
              >
                <span className="flex w-full items-center gap-1.5 font-medium leading-tight text-white/92">
                  {generateImage.busy ? (
                    <Loader2
                      className="h-3 w-3 shrink-0 animate-spin text-emerald-300/90"
                      aria-hidden
                    />
                  ) : (
                    <ImagePlus
                      className="h-3 w-3 shrink-0 opacity-75"
                      aria-hidden
                      strokeWidth={2}
                    />
                  )}
                  Generate image
                </span>
                <span className="text-[10px] font-normal leading-snug text-white/42">
                  {generateImage.busy ? "Generating…" : generateImage.subtitle}
                </span>
              </button>
              <div className="mx-2 my-0.5 h-px bg-white/[0.07]" role="separator" />
              <button
                type="button"
                role="menuitem"
                disabled={exportBlocked}
                className={cn(
                  "flex w-full flex-col gap-0 px-2.5 py-2 text-left text-[11px] transition-colors",
                  exportBlocked
                    ? "cursor-not-allowed opacity-50"
                    : "text-white/90 hover:bg-white/[0.06]",
                )}
                title={exportHint}
                onClick={() => {
                  if (exportBlocked) return;
                  exportPdf.onExport();
                  setOpen(false);
                }}
              >
                <span className="flex w-full items-center gap-1.5 font-medium leading-tight text-white/92">
                  {exportPdf.busy ? (
                    <Loader2
                      className="h-3 w-3 shrink-0 animate-spin text-emerald-300/90"
                      aria-hidden
                    />
                  ) : (
                    <FileDown className="h-3 w-3 shrink-0 opacity-75" aria-hidden strokeWidth={2} />
                  )}
                  Export PDF
                </span>
                <span className="text-[10px] font-normal leading-snug text-white/42">
                  {exportHint}
                </span>
              </button>
              {menuFooterHint?.trim() ? (
                <p className="mx-2 mb-1 mt-0.5 border-t border-white/[0.06] px-0.5 pt-1.5 text-[9px] leading-snug text-white/32">
                  {menuFooterHint.trim()}
                </p>
              ) : null}
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}
