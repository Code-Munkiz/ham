/**
 * Opens the in-shell chat drawer on non-chat `/workspace/*` routes.
 */
import { cn } from "@/lib/utils";
import { hamWorkspaceLogoUrl } from "@/lib/ham/publicAssets";

export type WorkspaceChatFloatingToggleProps = {
  onOpen: () => void;
};

export function WorkspaceChatFloatingToggle({ onOpen }: WorkspaceChatFloatingToggleProps) {
  const brand = hamWorkspaceLogoUrl();

  return (
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        "pointer-events-auto fixed z-50 flex h-12 w-12 items-center justify-center overflow-hidden rounded-full shadow-lg transition",
        "border border-white/15 bg-[#061018] hover:brightness-110 active:scale-95",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7dd3fc]",
        "bottom-[max(1rem,calc(3.75rem+env(safe-area-inset-bottom,0px)))] right-4 md:bottom-6 md:right-6",
      )}
      aria-label="Open workspace chat panel"
      title="Open chat"
    >
      <img src={brand} alt="" className="h-9 w-9 object-contain" width={36} height={36} />
    </button>
  );
}
