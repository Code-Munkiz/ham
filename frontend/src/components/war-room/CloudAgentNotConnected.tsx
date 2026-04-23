import { Radio } from "lucide-react";

export type CloudAgentNotConnectedProps = {
  onOpenProjectsRegistry?: () => void;
};

/**
 * Shown for Cloud Agent tabs when `active_cloud_agent_id` is absent.
 * Intentional empty state: guides attach / launch without feeling like a dead box.
 */
export function CloudAgentNotConnected({ onOpenProjectsRegistry }: CloudAgentNotConnectedProps) {
  return (
    <div className="flex min-h-0 flex-1 flex-col justify-center">
      <div className="mx-auto w-full max-w-md px-4 py-8 sm:px-6">
        <p className="text-[9px] font-black uppercase tracking-[0.2em] text-white/30">Execution</p>
        <div className="mt-3 rounded-lg border border-white/10 bg-gradient-to-b from-white/[0.04] to-black/20 px-4 py-6 sm:px-6 text-center">
          <div
            className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-lg border border-[#00E5FF]/20 bg-[#00E5FF]/5"
            aria-hidden
          >
            <Radio className="h-6 w-6 text-[#00E5FF]/60" />
          </div>
          <p className="text-[12px] font-black uppercase tracking-[0.2em] text-white/80">No active mission</p>
          <p className="mt-1 text-[12px] font-medium leading-relaxed text-white/50">
            The tracker and transcript need a Cloud Agent id. HAM is ready on the left.
          </p>
          <ul className="mt-4 space-y-2 text-left text-[12px] font-medium text-white/45">
            <li className="flex gap-2">
              <span className="text-[#FF6B00]">1.</span>
              <span>Launch a mission from the composer when uplink is Cloud (opens split view).</span>
            </li>
            <li className="flex gap-2">
              <span className="text-[#FF6B00]">2.</span>
              <span>Or bind an existing agent id under Projects → Active mission.</span>
            </li>
          </ul>
          {onOpenProjectsRegistry ? (
            <button
              type="button"
              onClick={onOpenProjectsRegistry}
              className="mt-6 w-full rounded border border-white/10 bg-white/[0.04] py-2.5 text-[10px] font-black uppercase tracking-widest text-white/60 transition-colors hover:border-[#00E5FF]/40 hover:text-[#00E5FF]/90"
            >
              Open projects registry
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
