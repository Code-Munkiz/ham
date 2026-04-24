import * as React from "react";
import { Orbit, RefreshCw, ExternalLink, Package, AlertCircle, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { isHamDesktopShell } from "@/lib/ham/desktopConfig";
import { getDesktopBundleApi } from "@/lib/ham/desktopBundleBridge";
import { fetchHermesGatewaySnapshot, type HermesGatewaySnapshot } from "@/lib/ham/api";
import { HermesOperatorConnectionStrip } from "@/components/hermes/HermesOperatorConnectionStrip";

type CuratedList = { schema_version?: number; description?: string; catalog_ids?: string[] };

export function DesktopBundlePanel() {
  const bundle = getDesktopBundleApi();
  const isDesktop = isHamDesktopShell();

  const [probe, setProbe] = React.useState<
    import("@/lib/ham/desktopBundleBridge").HermesCliProbeResult | null
  >(null);
  const [curated, setCurated] = React.useState<CuratedList | null>(null);
  const [snippet, setSnippet] = React.useState<string | null>(null);
  const [apiSnapshot, setApiSnapshot] = React.useState<HermesGatewaySnapshot | null>(null);
  const [apiSnapErr, setApiSnapErr] = React.useState<string | null>(null);
  const [err, setErr] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);

  const load = React.useCallback(async () => {
    if (!bundle) return;
    setLoading(true);
    setErr(null);
    setApiSnapErr(null);
    try {
      const p = await bundle.hermesCliProbe();
      setProbe(p);
      const j = await bundle.readCuratedFile("default-curated-skills.json");
      if (j.ok) {
        try {
          setCurated(JSON.parse(j.text) as CuratedList);
        } catch {
          setErr("Invalid default-curated-skills.json in bundle");
        }
      }
      const s = await bundle.readCuratedFile("ham-api-env.snippet");
      if (s.ok) setSnippet(s.text);
      try {
        const shot = await fetchHermesGatewaySnapshot();
        setApiSnapshot(shot);
      } catch (e) {
        setApiSnapshot(null);
        setApiSnapErr(e instanceof Error ? e.message : "Gateway snapshot failed");
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }, [bundle]);

  React.useEffect(() => {
    void load();
  }, [load]);

  if (!isDesktop || !bundle) {
    return (
      <div className="rounded-xl border border-white/10 bg-black/30 p-8 space-y-4 max-w-2xl">
        <div className="flex items-center gap-3 text-white/50">
          <Package className="h-5 w-5 text-[#FF6B00]" />
          <h3 className="text-sm font-black uppercase tracking-widest">HAM + Hermes bundle</h3>
        </div>
        <p className="text-xs text-white/40 leading-relaxed">
          The curated Hermes setup guide and CLI check run inside the <span className="text-white/60">HAM Desktop</span>{" "}
          Electron app. In the web dashboard, use the same repo docs and install Hermes on your host manually.
        </p>
        <a
          className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-[#FF6B00] hover:underline"
          href="https://github.com/NousResearch/hermes-agent"
          target="_blank"
          rel="noreferrer"
        >
          Hermes Agent (upstream) <ExternalLink className="h-3 w-3" />
        </a>
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-3xl">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="text-[11px] text-white/45 leading-relaxed">
          Shipped <span className="text-white/60">curated</span> docs and default skill <span className="font-mono">catalog_id</span>{" "}
          pins. The <span className="text-white/50">local</span> <span className="font-mono">hermes</span> binary (below) is separate from
          Ham API <span className="font-mono">HERMES_GATEWAY_*</span> (used for <span className="font-mono">/api/chat</span> when
          <span className="font-mono"> http</span> mode). TTY menus stay in a real terminal; see Command Center for Path B limits.
        </p>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-white/10 text-[10px] font-black uppercase tracking-widest text-white/60 hover:text-[#FF6B00] hover:border-[#FF6B00]/30 disabled:opacity-50"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
          Re-check CLI
        </button>
      </div>

      {err ? (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-xs text-amber-100/90 flex items-start gap-2">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          {err}
        </div>
      ) : null}

      {apiSnapErr ? (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-[11px] text-amber-200/80 flex items-start gap-2">
          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
          <span>
            Ham API snapshot unavailable ({apiSnapErr}). Is the API running and <span className="font-mono">VITE_HAM_API</span>{" "}
            correct?
          </span>
        </div>
      ) : null}
      {apiSnapshot?.operator_connection ? <HermesOperatorConnectionStrip snapshot={apiSnapshot} /> : null}

      <div className="rounded-xl border border-white/10 bg-[#0c0c0c] p-5 space-y-3">
        <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-white/35">
          <Orbit className="h-4 w-4 text-[#FF6B00]" />
          Hermes CLI
        </div>
        {probe == null && loading ? (
          <p className="text-xs text-white/30">Checking…</p>
        ) : probe?.ok ? (
          <div className="flex items-start gap-2 text-sm text-emerald-200/90">
            <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" />
            <span className="font-mono text-[11px]">{probe.versionLine}</span>
          </div>
        ) : (
          <div className="space-y-2 text-xs text-white/50">
            <div className="flex items-start gap-2 text-amber-200/80">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>Not found on PATH or failed to run. Install Hermes, then re-check.</span>
            </div>
            {probe?.ok === false ? (
              <p className="font-mono text-[10px] text-white/25">{probe.error}</p>
            ) : null}
          </div>
        )}
        <button
          type="button"
          onClick={async () => {
            const api = getDesktopBundleApi();
            if (api) await api.openHermesUpstreamDocs();
          }}
          className="inline-flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-[#FF6B00] hover:underline"
        >
          Open upstream Hermes docs <ExternalLink className="h-3 w-3" />
        </button>
      </div>

      <div className="rounded-xl border border-white/10 bg-[#0c0c0c] p-5 space-y-3">
        <h4 className="text-[10px] font-black uppercase tracking-widest text-white/35">Default curated skill IDs</h4>
        {curated?.catalog_ids?.length ? (
          <ul className="list-disc pl-5 space-y-1 font-mono text-[10px] text-white/55">
            {curated.catalog_ids.map((id) => (
              <li key={id}>{id}</li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-white/30">No list loaded. Re-check after fixing bundle files.</p>
        )}
        <p className="text-[9px] text-white/25 uppercase tracking-widest">
          Install via Hermes; HAM lists these as suggestions only.
        </p>
      </div>

      {snippet ? (
        <div className="rounded-xl border border-white/10 bg-[#0c0c0c] p-5 space-y-2">
          <h4 className="text-[10px] font-black uppercase tracking-widest text-white/35">Ham API env snippet (example)</h4>
          <pre className="text-[9px] font-mono text-white/45 whitespace-pre-wrap overflow-x-auto p-3 rounded bg-black/50 border border-white/5">
            {snippet}
          </pre>
        </div>
      ) : null}
    </div>
  );
}
