import { Radio } from "lucide-react";

/**
 * Shown for Cloud Agent tabs when `active_cloud_agent_id` is absent.
 * Not empty shells — explicit not-connected state per spec.
 */
export function CloudAgentNotConnected() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[200px] px-6 py-10 border border-white/10 bg-black/40 text-center">
      <Radio className="h-10 w-10 text-[#00E5FF]/40 mb-4" aria-hidden />
      <p className="text-[11px] font-black uppercase tracking-[0.2em] text-[#00E5FF]/90 mb-2">Not connected</p>
      <p className="text-[10px] font-bold text-white/40 uppercase tracking-widest leading-relaxed max-w-sm">
        No active Cloud Agent mission. Launch an agent from CI/API or set an agent id in Projects to hydrate
        tracker, transcript, and artifacts.
      </p>
    </div>
  );
}
