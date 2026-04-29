import * as React from "react";
import { ChevronRight, ClipboardCopy } from "lucide-react";
import { cn } from "@/lib/utils";
import type { CapabilityDirectoryRecord } from "@/lib/ham/api";

function DirectoryTrustBadge({ tier }: { tier: string }) {
  const muted =
    tier === "first_party"
      ? "border-emerald-500/40 text-emerald-400/80 bg-emerald-500/5"
      : tier === "verified_org"
        ? "border-blue-500/40 text-blue-400/80 bg-blue-500/5"
        : "border-white/15 text-white/50 bg-white/[0.03]";
  return (
    <span
      className={cn(
        "text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border",
        muted,
      )}
    >
      {tier.replace(/_/g, " ")}
    </span>
  );
}

export interface CapabilityBundleCardProps {
  bundle: CapabilityDirectoryRecord;
  selected: boolean;
  onInspect: () => void;
  onCopyId: () => void;
}

export function CapabilityBundleCard({
  bundle,
  selected,
  onInspect,
  onCopyId,
}: CapabilityBundleCardProps) {
  const readOnly =
    bundle.mutability === "read_only" ||
    bundle.mutability === "launch_via_existing_apis_only";
  return (
    <div
      className={cn(
        "flex flex-col p-6 bg-[#0a0a0a] border rounded-xl transition-all",
        selected ? "border-[#FF6B00]/50 ring-1 ring-[#FF6B00]/20" : "border-white/5 hover:border-[#FF6B00]/35",
      )}
    >
      <div className="flex justify-between items-start gap-4 mb-3">
        <div className="space-y-2 flex-1 min-w-0">
          <h3 className="text-sm font-black uppercase tracking-wide text-[#FF6B00] leading-tight">
            {bundle.display_name}
          </h3>
          <p className="text-[10px] font-bold text-white/35 leading-relaxed line-clamp-3">
            {bundle.summary}
          </p>
        </div>
        <ChevronRight
          className={cn(
            "h-4 w-4 shrink-0",
            selected ? "text-[#FF6B00]" : "text-white/20",
          )}
        />
      </div>
      <div className="flex flex-wrap gap-2 mb-3">
        <DirectoryTrustBadge tier={bundle.trust_tier} />
        <span
          className={cn(
            "text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border",
            readOnly
              ? "border-cyan-500/35 text-cyan-300/80 bg-cyan-500/5"
              : "border-amber-500/35 text-amber-200/80 bg-amber-500/5",
          )}
        >
          {readOnly ? "Read-only / policy" : bundle.mutability.replace(/_/g, " ")}
        </span>
        {bundle.preview_available ? (
          <span className="text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border border-white/15 text-white/45">
            Preview (future)
          </span>
        ) : null}
        <span className="text-[8px] font-black uppercase tracking-widest px-2 py-0.5 rounded border border-white/10 text-white/35">
          Apply: off
        </span>
      </div>
      <div className="flex flex-wrap gap-1.5 mb-3">
        {bundle.required_backends.map((b) => (
          <span
            key={b}
            className="text-[8px] font-mono text-white/40 border border-white/10 px-1.5 py-0.5 rounded"
          >
            {b}
          </span>
        ))}
      </div>
      {bundle.surfaces.length > 0 && (
        <p className="text-[9px] text-white/30 mb-2">
          <span className="text-white/40 font-black uppercase tracking-wider">Surfaces: </span>
          {bundle.surfaces.map((s) => s.route).join(", ")}
        </p>
      )}
      {bundle.risks.length > 0 && (
        <p className="text-[9px] text-amber-200/70 mb-3">
          {bundle.risks.length} risk{bundle.risks.length === 1 ? "" : "s"} noted
        </p>
      )}
      <div className="flex flex-wrap gap-2 mt-auto pt-2 border-t border-white/5">
        <button
          type="button"
          onClick={onInspect}
          className="text-[9px] font-black uppercase tracking-widest px-3 py-2 rounded-lg bg-[#FF6B00]/15 border border-[#FF6B00]/40 text-[#FF6B00] hover:bg-[#FF6B00]/25"
        >
          Inspect bundle
        </button>
        <button
          type="button"
          onClick={onCopyId}
          className="text-[9px] font-black uppercase tracking-widest px-3 py-2 rounded-lg border border-white/15 text-white/50 hover:text-white hover:bg-white/5 flex items-center gap-1.5"
        >
          <ClipboardCopy className="h-3 w-3" />
          Copy ID
        </button>
      </div>
      <p className="mt-3 text-[9px] font-mono text-white/15 truncate">{bundle.id}</p>
    </div>
  );
}
