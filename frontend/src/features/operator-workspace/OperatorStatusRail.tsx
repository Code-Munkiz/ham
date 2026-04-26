import { History, MessageSquare, Radio, Rocket } from "lucide-react";

type OperatorStatusRailProps = {
  activeCloudAgentId: string | null;
  cloudMissionHandling: string;
  onOpenCloudAgentLaunch: () => void;
  onCloudAgentPreview: () => void;
  cloudAgentPreviewDisabled: boolean;
  cloudAgentPreviewTitle: string;
  onOpenHistory: () => void;
  onOpenProjects: () => void;
};

export function OperatorStatusRail({
  activeCloudAgentId,
  cloudMissionHandling,
  onOpenCloudAgentLaunch,
  onCloudAgentPreview,
  cloudAgentPreviewDisabled,
  cloudAgentPreviewTitle,
  onOpenHistory,
  onOpenProjects,
}: OperatorStatusRailProps) {
  return (
    <section className="rounded-2xl border border-white/10 bg-[#0f1520]/80 p-3 shadow-[0_12px_36px_rgba(0,0,0,0.25)]">
      <p className="text-[11px] font-semibold uppercase tracking-[0.13em] text-white/50">
        Cloud Agent capability
      </p>
      <p className="mt-1 text-xs text-white">
        {activeCloudAgentId
          ? `Active mission: ${activeCloudAgentId}`
          : "No mission attached"}
      </p>
      <p className="text-[11px] text-white/45">
        Handling mode: {cloudMissionHandling}
      </p>

      <div className="mt-3 grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={onOpenCloudAgentLaunch}
          className="inline-flex items-center justify-center gap-1 rounded-xl border border-cyan-400/35 bg-cyan-400/10 px-2 py-1.5 text-xs font-medium text-cyan-200"
        >
          <Rocket className="h-3.5 w-3.5" />
          Launch
        </button>
        <button
          type="button"
          onClick={onCloudAgentPreview}
          disabled={cloudAgentPreviewDisabled}
          title={cloudAgentPreviewTitle}
          className="inline-flex items-center justify-center gap-1 rounded-xl border border-white/15 bg-black/20 px-2 py-1.5 text-xs text-white/75 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Radio className="h-3.5 w-3.5" />
          Preview
        </button>
        <button
          type="button"
          onClick={onOpenHistory}
          className="inline-flex items-center justify-center gap-1 rounded-xl border border-white/15 bg-black/20 px-2 py-1.5 text-xs text-white/75"
        >
          <MessageSquare className="h-3.5 w-3.5" />
          History
        </button>
        <button
          type="button"
          onClick={onOpenProjects}
          className="inline-flex items-center justify-center gap-1 rounded-xl border border-white/15 bg-black/20 px-2 py-1.5 text-xs text-white/75"
        >
          <History className="h-3.5 w-3.5" />
          Projects
        </button>
      </div>
    </section>
  );
}

