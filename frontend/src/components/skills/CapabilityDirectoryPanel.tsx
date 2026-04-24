import * as React from "react";
import { LayoutGrid, ShieldAlert } from "lucide-react";
import {
  fetchCapabilityDirectoryBundle,
  fetchCapabilityDirectoryBundles,
  fetchCapabilityDirectoryIndex,
  type CapabilityDirectoryBundleResponse,
  type CapabilityDirectoryBundlesResponse,
  type CapabilityDirectoryIndexResponse,
  type CapabilityDirectoryRecord,
} from "@/lib/ham/api";
import { CapabilityBundleCard } from "./CapabilityBundleCard";
import { CapabilityBundleDetail } from "./CapabilityBundleDetail";

export function CapabilityDirectoryPanel() {
  const [index, setIndex] = React.useState<CapabilityDirectoryIndexResponse | null>(null);
  const [bundlesRes, setBundlesRes] = React.useState<CapabilityDirectoryBundlesResponse | null>(
    null,
  );
  const [loadErr, setLoadErr] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);

  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [detailRes, setDetailRes] = React.useState<CapabilityDirectoryBundleResponse | null>(null);
  const [detailErr, setDetailErr] = React.useState<string | null>(null);
  const [detailLoading, setDetailLoading] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setLoadErr(null);
      try {
        const [idx, b] = await Promise.all([
          fetchCapabilityDirectoryIndex(),
          fetchCapabilityDirectoryBundles(),
        ]);
        if (cancelled) return;
        setIndex(idx);
        setBundlesRes(b);
      } catch (e) {
        if (!cancelled) {
          setLoadErr(e instanceof Error ? e.message : String(e));
          setIndex(null);
          setBundlesRes(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    if (!selectedId) {
      setDetailRes(null);
      setDetailErr(null);
      setDetailLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      setDetailLoading(true);
      setDetailErr(null);
      try {
        const d = await fetchCapabilityDirectoryBundle(selectedId);
        if (!cancelled) setDetailRes(d);
      } catch (e) {
        if (!cancelled) {
          setDetailRes(null);
          setDetailErr(e instanceof Error ? e.message : String(e));
        }
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const bundles: CapabilityDirectoryRecord[] = bundlesRes?.bundles ?? [];

  const copyId = async (id: string) => {
    try {
      await navigator.clipboard.writeText(id);
    } catch {
      /* ignore */
    }
  };

  if (loading) {
    return (
      <section className="space-y-4 py-4">
        <p className="text-[11px] text-white/40 flex items-center gap-2">
          <LayoutGrid className="h-4 w-4 animate-pulse text-[#FF6B00]" />
          Loading capability directory…
        </p>
      </section>
    );
  }

  if (loadErr) {
    return (
      <section className="space-y-4 py-4">
        <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-4 text-red-200/90 text-[11px] leading-relaxed">
          <p className="font-black uppercase tracking-wider text-[10px] mb-2 flex items-center gap-2">
            <ShieldAlert className="h-4 w-4" />
            Capability directory unavailable
          </p>
          <p>{loadErr}</p>
          <p className="mt-2 text-white/40">
            Confirm you are signed in (if Clerk is enabled) and the API includes{" "}
            <code className="text-white/55">/api/capability-directory</code>.
          </p>
        </div>
      </section>
    );
  }

  if (!index || !bundlesRes) {
    return (
      <section className="py-4 text-[11px] text-white/35">
        No directory data returned from the API.
      </section>
    );
  }

  return (
    <section className="space-y-8 py-4">
      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-5 space-y-3">
        <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.25em] text-[#FF6B00]/90">
          <LayoutGrid className="h-4 w-4" />
          Registry summary
        </div>
        <p className="text-[10px] text-white/45 leading-relaxed">
          <span className="text-white/55 font-mono">{index.registry_id}</span>
          <span className="text-white/25 mx-2">·</span>
          <span className="text-white/35">{index.schema_version}</span>
        </p>
        {index.no_execution_notice ? (
          <p className="text-[10px] text-cyan-200/85 border border-cyan-500/20 bg-cyan-500/5 rounded-lg p-3 leading-relaxed">
            {index.no_execution_notice}
          </p>
        ) : null}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
          <div className="rounded-lg border border-white/10 bg-black/30 p-3">
            <div className="text-[20px] font-black text-white/90">{index.counts.capabilities}</div>
            <div className="text-[8px] font-black uppercase tracking-widest text-white/35">
              Capabilities
            </div>
          </div>
          <div className="rounded-lg border border-white/10 bg-black/30 p-3">
            <div className="text-[20px] font-black text-white/90">{index.counts.bundles}</div>
            <div className="text-[8px] font-black uppercase tracking-widest text-white/35">
              Bundles
            </div>
          </div>
          <div className="rounded-lg border border-white/10 bg-black/30 p-3">
            <div className="text-[20px] font-black text-white/90">
              {index.counts.profile_templates}
            </div>
            <div className="text-[8px] font-black uppercase tracking-widest text-white/35">
              Profile templates
            </div>
          </div>
          <div className="rounded-lg border border-white/10 bg-black/30 p-3">
            <div className="text-[10px] font-black text-emerald-300/90">
              {index.apply_available_globally ? "On" : "Off"}
            </div>
            <div className="text-[8px] font-black uppercase tracking-widest text-white/35">
              Apply (phase 1)
            </div>
          </div>
        </div>
        <div>
          <p className="text-[9px] font-black uppercase text-white/35 mb-2">Trust tier counts</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(index.trust_tier_counts).map(([k, v]) => (
              <span
                key={k}
                className="text-[9px] font-mono px-2 py-1 rounded border border-white/10 text-white/50"
              >
                {k}: {v}
              </span>
            ))}
          </div>
        </div>
        {index.registry_note ? (
          <p className="text-[10px] text-white/40 italic">{index.registry_note}</p>
        ) : null}
      </div>

      <div>
        <h2 className="text-[10px] font-black uppercase tracking-[0.3em] text-white/40 mb-4">
          Bundles ({bundles.length})
        </h2>
        {bundles.length === 0 ? (
          <p className="text-[11px] text-white/35">No bundles in this registry.</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {bundles.map((b) => (
              <CapabilityBundleCard
                key={b.id}
                bundle={b}
                selected={selectedId === b.id}
                onInspect={() => setSelectedId(b.id)}
                onCopyId={() => void copyId(b.id)}
              />
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="text-[10px] font-black uppercase tracking-[0.3em] text-white/40 mb-3">
          Bundle detail
        </h2>
        <CapabilityBundleDetail
          bundle={detailRes?.bundle ?? null}
          loading={detailLoading}
          error={detailErr}
          notice={detailRes?.no_execution_notice ?? null}
        />
      </div>
    </section>
  );
}
