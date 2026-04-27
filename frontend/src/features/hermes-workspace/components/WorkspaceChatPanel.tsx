/**
 * In-page chat drawer — same `WorkspaceChatScreen` + stream adapter as full-page chat.
 */
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { ExternalLink, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { WorkspaceChatScreen } from "../screens/chat/WorkspaceChatScreen";

export type WorkspaceChatPanelProps = {
  open: boolean;
  onClose: () => void;
};

export function WorkspaceChatPanel({ open, onClose }: WorkspaceChatPanelProps) {
  const navigate = useNavigate();

  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      <button
        type="button"
        className="fixed inset-0 z-[60] bg-black/45 backdrop-blur-[2px]"
        aria-label="Close chat panel"
        onClick={onClose}
      />
      <div
        className="fixed inset-y-0 right-0 z-[70] flex w-[min(100vw,28rem)] flex-col border-l border-white/[0.08] bg-[#030a10] shadow-2xl sm:w-[min(100vw,32rem)]"
        role="dialog"
        aria-modal="true"
        aria-label="Workspace chat"
      >
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-white/[0.06] bg-[#040d14]/95 px-3 py-2.5">
          <p className="min-w-0 truncate text-[13px] font-semibold text-white/90">Chat</p>
          <div className="flex shrink-0 items-center gap-1">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-8 gap-1 px-2 text-[11px] text-[#7dd3fc]"
              onClick={() => {
                onClose();
                navigate("/workspace/chat");
              }}
            >
              <ExternalLink className="h-3.5 w-3.5" strokeWidth={1.5} />
              <span className="hidden sm:inline">Full chat</span>
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-white/70"
              onClick={onClose}
              aria-label="Close chat panel"
            >
              <X className="h-4 w-4" strokeWidth={1.5} />
            </Button>
          </div>
        </div>
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <WorkspaceChatScreen embedMode />
        </div>
      </div>
    </>
  );
}
