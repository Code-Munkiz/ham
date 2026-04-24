import { Link } from "react-router-dom";
import { ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";
import type { CapabilityDirectoryRecord } from "@/lib/ham/api";

/** Routes we allow as "open related surface" from directory (in-app only). */
const SAFE_ROUTE_PREFIXES = [
  "/shop",
  "/skills",
  "/hermes",
  "/chat",
  "/agents",
  "/settings",
  "/control-plane",
] as const;

function isSafeSurfaceRoute(route: string): boolean {
  const r = route.trim();
  if (!r.startsWith("/")) return false;
  return SAFE_ROUTE_PREFIXES.some((p) => r === p || r.startsWith(`${p}/`));
}

export interface CapabilityBundleDetailProps {
  bundle: CapabilityDirectoryRecord | null;
  loading: boolean;
  error: string | null;
  notice?: string | null;
}

export function CapabilityBundleDetail({
  bundle,
  loading,
  error,
  notice,
}: CapabilityBundleDetailProps) {
  if (loading) {
    return (
      <div className="rounded-xl border border-white/10 bg-[#080808] p-6 text-[11px] text-white/40">
        Loading bundle detail…
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/5 p-6 text-[11px] text-red-200/90">
        {error}
      </div>
    );
  }
  if (!bundle) {
    return (
      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6 text-[11px] text-white/35">
        Select a bundle and choose <span className="text-[#FF6B00]/90">Inspect bundle</span> to view
        metadata. This directory is read-only (no install or apply).
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-[#FF6B00]/25 bg-[#080808] p-6 space-y-4 text-[11px]">
      {notice ? (
        <p className="text-[10px] text-cyan-200/80 border border-cyan-500/25 bg-cyan-500/5 rounded-lg p-3">
          {notice}
        </p>
      ) : null}
      <div>
        <h3 className="text-lg font-black text-[#FF6B00] uppercase tracking-tight">
          {bundle.display_name}
        </h3>
        <p className="text-white/45 mt-1 leading-relaxed">{bundle.description}</p>
      </div>
      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[10px]">
        <div>
          <dt className="text-white/30 font-black uppercase tracking-wider">Trust</dt>
          <dd className="text-white/70 mt-0.5">{bundle.trust_tier}</dd>
        </div>
        <div>
          <dt className="text-white/30 font-black uppercase tracking-wider">Version</dt>
          <dd className="text-white/70 mt-0.5 font-mono">{bundle.version}</dd>
        </div>
        <div>
          <dt className="text-white/30 font-black uppercase tracking-wider">Mutability</dt>
          <dd className="text-white/70 mt-0.5">{bundle.mutability.replace(/_/g, " ")}</dd>
        </div>
        <div>
          <dt className="text-white/30 font-black uppercase tracking-wider">Preview / Apply</dt>
          <dd className="text-white/70 mt-0.5">
            preview_available: {String(bundle.preview_available)} · apply_available:{" "}
            <span className={bundle.apply_available ? "text-amber-300" : "text-emerald-300/90"}>
              {String(bundle.apply_available)}
            </span>
          </dd>
        </div>
      </dl>
      <div>
        <p className="text-[9px] font-black uppercase text-white/35 mb-1">Required backends</p>
        <ul className="flex flex-wrap gap-1.5">
          {bundle.required_backends.map((b) => (
            <li
              key={b}
              className="font-mono text-[9px] text-white/50 border border-white/10 px-2 py-0.5 rounded"
            >
              {b}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <p className="text-[9px] font-black uppercase text-white/35 mb-1">Surfaces</p>
        <ul className="space-y-2">
          {bundle.surfaces.map((s) => (
            <li
              key={`${s.route}-${s.label}`}
              className="flex flex-wrap items-center gap-2 text-white/55"
            >
              <span className="font-mono text-[10px]">{s.route}</span>
              <span className="text-white/30">— {s.label}</span>
              {isSafeSurfaceRoute(s.route) ? (
                <Link
                  to={s.route}
                  className={cn(
                    "inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-wider",
                    "text-[#FF6B00]/90 hover:text-[#FF6B00]",
                  )}
                >
                  Open related surface
                  <ExternalLink className="h-3 w-3" />
                </Link>
              ) : null}
            </li>
          ))}
        </ul>
      </div>
      {bundle.tags.length > 0 && (
        <div>
          <p className="text-[9px] font-black uppercase text-white/35 mb-1">Tags</p>
          <div className="flex flex-wrap gap-1.5">
            {bundle.tags.map((t) => (
              <span
                key={t}
                className="text-[8px] font-bold uppercase tracking-wide px-2 py-0.5 rounded border border-white/10 text-white/40"
              >
                {t}
              </span>
            ))}
          </div>
        </div>
      )}
      {bundle.risks.length > 0 && (
        <div className="rounded-lg border border-amber-500/25 bg-amber-500/5 p-3 space-y-1">
          <p className="text-[9px] font-black uppercase text-amber-200/90">Risks</p>
          <ul className="list-disc pl-4 text-amber-100/80 text-[10px] space-y-1">
            {bundle.risks.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      )}
      {bundle.evidence_expectations.length > 0 && (
        <div>
          <p className="text-[9px] font-black uppercase text-white/35 mb-1">Evidence expectations</p>
          <ul className="list-disc pl-4 text-white/50 text-[10px] space-y-1">
            {bundle.evidence_expectations.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-[9px] font-mono text-white/25 pt-2 border-t border-white/5">id: {bundle.id}</p>
    </div>
  );
}
