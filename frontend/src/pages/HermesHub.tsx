/**
 * Hermes-forward control plane hub: honest gateway + runtime skills status.
 * Deep links to /skills for catalog/install — does not duplicate that UI.
 */
import * as React from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  AppWindow,
  ArrowRight,
  BookOpen,
  Info,
  Orbit,
  Radio,
  Shield,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  fetchBrowserRuntimePolicy,
  fetchHermesHubSnapshot,
  type BrowserRuntimePolicySnapshot,
  type HermesHubSnapshot,
} from "@/lib/ham/api";

export default function HermesHub() {
  const [snap, setSnap] = React.useState<HermesHubSnapshot | null>(null);
  const [err, setErr] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [browserPolicy, setBrowserPolicy] = React.useState<BrowserRuntimePolicySnapshot | null>(null);
  const [browserPolicyErr, setBrowserPolicyErr] = React.useState<string | null>(null);
  const [browserPolicyLoading, setBrowserPolicyLoading] = React.useState(true);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setErr(null);
      try {
        const data = await fetchHermesHubSnapshot();
        if (!cancelled) setSnap(data);
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Failed to load Hermes hub");
          setSnap(null);
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
    let cancelled = false;
    (async () => {
      setBrowserPolicyLoading(true);
      setBrowserPolicyErr(null);
      try {
        const p = await fetchBrowserRuntimePolicy();
        if (!cancelled) setBrowserPolicy(p);
      } catch (e) {
        if (!cancelled) {
          setBrowserPolicy(null);
          setBrowserPolicyErr(
            e instanceof Error ? e.message : "Failed to load browser policy",
          );
        }
      } finally {
        if (!cancelled) setBrowserPolicyLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const caps = snap?.skills_capabilities;

  return (
    <div className="h-full overflow-auto bg-[#000000] text-white/90">
      <div className="max-w-4xl mx-auto px-8 py-10 space-y-8">
        <header className="space-y-3">
          <div className="flex items-center gap-3 text-[#FF6B00]">
            <Orbit className="h-8 w-8 shrink-0" aria-hidden />
            <h1 className="text-2xl font-black tracking-tight text-white">Hermes</h1>
          </div>
          <p className="text-sm text-white/55 leading-relaxed max-w-2xl">
            HAM-native view of Hermes-related runtime signals: how dashboard chat uses a
            Hermes-compatible upstream from gateway configuration, in-browser live sessions use HAM
            Playwright and this host&apos;s{" "}
            <span className="text-white/75 font-semibold">browser policy</span> (see below), and
            what the API can do with{" "}
            <span className="text-white/75 font-semibold">Hermes runtime skills</span> (catalog /
            install). This is not a Hermes CLI mirror, there is no separate Hermes terminal API in
            HAM today, and it does not list agents or workflows — those surfaces are not in this
            repo yet.
          </p>
        </header>

        {loading && (
          <p className="text-xs font-bold uppercase tracking-widest text-white/40">Loading…</p>
        )}
        {err && (
          <div
            role="alert"
            className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100"
          >
            {err}
          </div>
        )}

        {snap && (
          <div className="grid gap-6 md:grid-cols-1">
            <section
              className={cn(
                "rounded-xl border border-white/10 bg-white/[0.03] p-6 space-y-4",
              )}
            >
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-white/45">
                <Radio className="h-4 w-4 text-[#FF6B00]" />
                Dashboard chat gateway
              </div>
              <div className="flex flex-wrap gap-2 items-center">
                <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded border border-white/15 bg-white/[0.05]">
                  HERMES_GATEWAY_MODE → {snap.gateway_mode}
                </span>
                {snap.gateway_mode === "openrouter" && (
                  <span
                    className={cn(
                      "text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded border",
                      snap.openrouter_chat_ready
                        ? "border-emerald-500/40 text-emerald-300/90"
                        : "border-amber-500/40 text-amber-200/90",
                    )}
                  >
                    OpenRouter {snap.openrouter_chat_ready ? "ready" : "not ready"}
                  </span>
                )}
                {snap.gateway_mode === "http" && (
                  <span
                    className={cn(
                      "text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded border",
                      snap.http_chat_ready
                        ? "border-emerald-500/40 text-emerald-300/90"
                        : "border-amber-500/40 text-amber-200/90",
                    )}
                  >
                    HTTP {snap.http_chat_ready ? "ready" : "not ready"}
                  </span>
                )}
              </div>
              <p className="text-sm text-white/70 leading-relaxed">{snap.dashboard_chat.summary}</p>
              <p className="text-[11px] text-white/45">
                <span className="text-white/55">
                  There is no dedicated Hermes terminal/TTY API in this codebase — shell or tool
                  access goes through the configured upstream in HTTP mode, or other HAM entry
                  points (e.g. Droid) when applicable.
                </span>{" "}
                Composer detail and model rows:{" "}
                <Link
                  to="/chat"
                  className="text-[#FF6B00] hover:underline font-semibold"
                >
                  Chat
                </Link>{" "}
                uses the API; raw catalog: <span className="font-mono">GET /api/models</span>.
              </p>
            </section>

            <section className="rounded-xl border border-white/10 bg-white/[0.03] p-6 space-y-4">
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-white/45">
                <AppWindow className="h-4 w-4 text-[#FF6B00]" />
                Browser runtime readiness
              </div>
              <p className="text-sm text-white/70 leading-relaxed">
                In HAM, the live browser is Playwright on this API host, enforced by{" "}
                <span className="text-white/85 font-semibold">browser policy</span> — not a
                separate Hermes-managed browser product. The same policy applies when you use the
                browser pane from{" "}
                <Link to="/chat" className="text-[#FF6B00] font-semibold hover:underline">
                  Chat
                </Link>{" "}
                in <span className="text-white/85">War Room</span> mode.
              </p>
              {browserPolicyLoading && (
                <p className="text-xs font-bold uppercase tracking-widest text-white/40">Loading…</p>
              )}
              {browserPolicyErr && (
                <div
                  role="alert"
                  className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-100"
                >
                  {browserPolicyErr}
                </div>
              )}
              {browserPolicy && !browserPolicyLoading && (
                <>
                  <div className="flex flex-wrap gap-2 items-center">
                    <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded border border-white/15 bg-white/[0.05]">
                      {browserPolicy.runtime_host}
                    </span>
                    {browserPolicy.streaming_supported ? (
                      <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded border border-emerald-500/40 text-emerald-200/90">
                        Streaming: on
                      </span>
                    ) : (
                      <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded border border-white/20 text-white/50">
                        Streaming: off
                      </span>
                    )}
                    <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded border border-white/15">
                      WebRTC {browserPolicy.webrtc_enabled ? "enabled" : "disabled"}
                    </span>
                    {browserPolicy.allow_private_network ? (
                      <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded border border-amber-500/40 text-amber-200/90">
                        Private network: allowed
                      </span>
                    ) : (
                      <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded border border-white/15">
                        Private network: blocked
                      </span>
                    )}
                    <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded border border-white/15">
                      TTL {browserPolicy.session_ttl_seconds}s
                    </span>
                  </div>
                  <p className="text-[10px] text-white/50 font-mono break-all">
                    <span className="text-white/40 not-italic">Policy endpoint </span>GET{" "}
                    /api/browser/policy
                  </p>
                  <div className="grid gap-2 md:grid-cols-2 text-[11px] text-white/60">
                    <div>
                      <div className="text-[10px] font-black uppercase tracking-widest text-white/40 mb-1">
                        Allowed domains
                      </div>
                      {browserPolicy.allowed_domains.length === 0 ? (
                        <p className="text-white/45">
                          (no allowlist; blocklist and private-network rules still apply)
                        </p>
                      ) : (
                        <ul className="list-disc pl-4 space-y-0.5">
                          {browserPolicy.allowed_domains.slice(0, 6).map((d) => (
                            <li key={d} className="font-mono break-all">
                              {d}
                            </li>
                          ))}
                          {browserPolicy.allowed_domains.length > 6 && (
                            <li className="list-none -ml-4 text-white/45">
                              +{browserPolicy.allowed_domains.length - 6} more
                            </li>
                          )}
                        </ul>
                      )}
                    </div>
                    <div>
                      <div className="text-[10px] font-black uppercase tracking-widest text-white/40 mb-1">
                        Blocked domains
                      </div>
                      {browserPolicy.blocked_domains.length === 0 ? (
                        <p className="text-white/45">(none)</p>
                      ) : (
                        <ul className="list-disc pl-4 space-y-0.5">
                          {browserPolicy.blocked_domains.slice(0, 6).map((d) => (
                            <li key={d} className="font-mono break-all">
                              {d}
                            </li>
                          ))}
                          {browserPolicy.blocked_domains.length > 6 && (
                            <li className="list-none -ml-4 text-white/45">
                              +{browserPolicy.blocked_domains.length - 6} more
                            </li>
                          )}
                        </ul>
                      )}
                    </div>
                  </div>
                </>
              )}
            </section>

            <section className="rounded-xl border border-white/10 bg-white/[0.03] p-6 space-y-4">
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-white/45">
                <BookOpen className="h-4 w-4 text-[#FF6B00]" />
                Hermes runtime skills
              </div>
              {caps && (
                <>
                  <div className="flex flex-wrap gap-2">
                    <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded border border-white/15">
                      Host mode: {caps.mode}
                    </span>
                    {caps.hermes_home_detected ? (
                      <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded border border-emerald-500/35 text-emerald-200/90">
                        Hermes home detected
                      </span>
                    ) : (
                      <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded border border-white/20 text-white/50">
                        No Hermes home on this host
                      </span>
                    )}
                    {caps.shared_runtime_install_supported === true && (
                      <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded border border-emerald-500/35 text-emerald-200/90">
                        Shared install supported
                      </span>
                    )}
                    {caps.skills_apply_writes_enabled === true && (
                      <span className="text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded border border-white/15">
                        Apply token set
                      </span>
                    )}
                  </div>
                  {caps.hermes_home_path_hint && (
                    <p className="font-mono text-[10px] text-white/50 break-all">
                      {caps.hermes_home_path_hint}
                    </p>
                  )}
                  {caps.mode === "remote_only" && (
                    <div className="flex gap-2 rounded-lg border border-amber-500/35 bg-amber-500/5 p-3 text-xs text-amber-100/90">
                      <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                      <span>
                        <strong className="text-amber-200">remote_only</strong> — catalog is
                        available; mutating installs are blocked on this deployment (API not
                        co-located with operator Hermes home).
                      </span>
                    </div>
                  )}
                  {(caps.warnings?.length ?? 0) > 0 && (
                    <ul className="list-disc pl-5 text-[11px] text-white/55 space-y-1">
                      {caps.warnings.map((w) => (
                        <li key={w}>{w}</li>
                      ))}
                    </ul>
                  )}
                </>
              )}
              <Link
                to="/skills"
                className="inline-flex items-center gap-2 text-sm font-bold text-[#FF6B00] hover:underline"
              >
                Open runtime skills catalog
                <ArrowRight className="h-4 w-4" />
              </Link>
            </section>

            <section className="rounded-xl border border-white/10 bg-white/[0.03] p-6 space-y-4">
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-white/45">
                <Info className="h-4 w-4 text-[#FF6B00]" />
                Scope in HAM (honest)
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <div className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest text-emerald-400/80 mb-2">
                    <Shield className="h-3.5 w-3.5" />
                    In this repo today
                  </div>
                  <ul className="text-[11px] text-white/60 space-y-2 leading-relaxed">
                    {snap.scope_notes.in_ham_today.map((line) => (
                      <li key={line} className="list-disc ml-4">
                        {line}
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <div className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest text-amber-400/80 mb-2">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    Not exposed here
                  </div>
                  <ul className="text-[11px] text-white/60 space-y-2 leading-relaxed">
                    {snap.scope_notes.not_in_ham_yet.map((line) => (
                      <li key={line} className="list-disc ml-4">
                        {line}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
              <p className="text-[10px] text-white/40 leading-relaxed">
                For HAM project-scoped agent identities (not Hermes CLI profiles), use{" "}
                <Link to="/agents" className="text-[#FF6B00] hover:underline font-semibold">
                  Agents
                </Link>
                .
              </p>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
