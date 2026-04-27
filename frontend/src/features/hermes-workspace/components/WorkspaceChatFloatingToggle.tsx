/**
 * Upstream `chat-panel-toggle.tsx`: fixed bottom-right launcher on non-chat workspace routes.
 * HAM uses route navigation to `/workspace/chat` (no side-panel chat transport).
 */
import { Link } from "react-router-dom";
import { MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";

export function WorkspaceChatFloatingToggle() {
  return (
    <Link
      to="/workspace/chat"
      className={cn(
        "pointer-events-auto fixed z-50 flex h-12 w-12 items-center justify-center rounded-full shadow-lg transition",
        "bg-[color:var(--theme-accent,#10b981)] text-white hover:brightness-110 active:scale-95",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7dd3fc]",
        /* Clear mobile tab bar (~3.5rem) + safe area; desktop matches upstream bottom-6 right-6 */
        "bottom-[max(1rem,calc(3.75rem+env(safe-area-inset-bottom,0px)))] right-4 md:bottom-6 md:right-6",
      )}
      aria-label="Open workspace chat"
      title="Open workspace chat"
    >
      <MessageSquare className="h-5 w-5" strokeWidth={1.75} aria-hidden />
    </Link>
  );
}
