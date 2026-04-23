import { Radio } from "lucide-react";

/**
 * Shown for Cloud Agent tabs when `active_cloud_agent_id` is absent.
 * Not empty shells — explicit not-connected state per spec.
 */
export function CloudAgentNotConnected() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[200px] px-6 py-10 border border-white/10 bg-black/40 text-center">
      <Radio className="h-10 w-10 text-[#00E5FF]/40 mb-4" aria-hidden />
      <p className="text-[13px] font-black uppercase tracking-[0.2em] text-[#00E5FF]/90 mb-2">Not connected</p>
      <p className="text-[13px] font-medium text-white/80 uppercase tracking-[0.02em] leading-[1.6] max-w-sm mb-1">
        No active mission.
      </p>
      <p className="text-[12px] font-bold text-white/50 uppercase tracking-wider leading-relaxed max-w-sm">
        Use Launch in the chat bar (Cloud uplink) or set an agent id under Projects to load tracker and transcript.
      </p>
    </div>
  );
}
