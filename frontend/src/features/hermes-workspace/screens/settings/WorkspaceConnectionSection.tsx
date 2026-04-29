import * as React from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { EnvironmentReadonlyPanel } from "@/components/workspace/UnifiedSettings";
import { LocalMachineConnectCta } from "../../components/LocalMachineConnectCta";
import {
  getLocalRuntimeBase,
  LOCAL_RUNTIME_SUGGESTIONS,
  setLocalRuntimeBase,
  testLocalRuntime,
  type LocalRuntimeTestResult,
} from "../../adapters/localRuntime";

/**
 * Connection: cloud vs local. Files + Terminal use the **local** Ham API on the user’s machine only;
 * no `VITE_HAM_API_BASE` for those — see Local runtime card.
 */
export function WorkspaceConnectionSection() {
  const [localUrl, setLocalUrl] = React.useState(() => getLocalRuntimeBase() ?? "");
  const [testing, setTesting] = React.useState(false);
  const [lastTest, setLastTest] = React.useState<LocalRuntimeTestResult | null>(null);
  const [advOpen, setAdvOpen] = React.useState(false);

  React.useEffect(() => {
    setLocalUrl(getLocalRuntimeBase() ?? "");
  }, []);

  React.useEffect(() => {
    const sync = () => {
      setLocalUrl(getLocalRuntimeBase() ?? "");
      setLastTest(null);
    };
    window.addEventListener("hww-local-runtime-changed", sync);
    return () => window.removeEventListener("hww-local-runtime-changed", sync);
  }, []);

  const handleSave = () => {
    setLocalRuntimeBase(localUrl.trim() || null);
    setLocalUrl(getLocalRuntimeBase() ?? "");
    setLastTest(null);
  };

  const handleTest = async () => {
    setTesting(true);
    setLastTest(null);
    try {
      const r = await testLocalRuntime(localUrl);
      setLastTest(r);
    } finally {
      setTesting(false);
    }
  };

  const statusLabel = lastTest
    ? lastTest.ok
      ? "Connected"
      : lastTest.message.includes("Missing") || lastTest.message.includes("Wrong API")
        ? "Wrong API"
        : "Not reachable"
    : null;

  return (
    <div className="space-y-8">
      <section className="hww-set-card rounded-2xl border border-white/[0.08] bg-white/[0.03] p-5 shadow-none md:p-6">
        <h2 className="text-base font-semibold leading-tight text-[#e8eef8]">Connection</h2>
        <p className="mt-1.5 text-[13px] leading-relaxed text-white/45">
          Chat, jobs, and most APIs use the normal cloud or configured API. <span className="text-white/55">Files</span> and{" "}
          <span className="text-white/55">Terminal</span> use a <em>separate</em> connection: the Ham process on this
          computer, not Cloud Run, so the browser can reach your local disk and shell.
        </p>
        <p className="mt-3 text-[13px] leading-relaxed text-white/40">
          Keys and providers:{" "}
          <Link
            className="text-[#7dd3fc] underline decoration-white/10 underline-offset-2 hover:decoration-[#7dd3fc]/50"
            to="/workspace/settings?section=hermes"
          >
            Model &amp; provider
          </Link>
          .
        </p>
      </section>

      <section className="hww-set-card rounded-2xl border border-white/[0.08] bg-white/[0.04] p-5 shadow-none md:p-6">
        <h3 className="text-sm font-semibold text-white/90">Local machine connection</h3>
        <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-white/42">
          Connect this browser to the HAM API on this computer. Files and Terminal stay local; the cloud cannot read
          your disk.
        </p>

        <div className="mt-4">
          <LocalMachineConnectCta variant="card" showOpenSettings={false} showOpenFiles />
        </div>

        <div className="mt-4">
          <button
            type="button"
            onClick={() => setAdvOpen((o) => !o)}
            className="text-[12px] text-[#7dd3fc] underline decoration-white/10 underline-offset-2 hover:decoration-[#7dd3fc]/50"
          >
            {advOpen ? "Hide advanced" : "Advanced — runtime URL, test, filesystem and CORS notes"}
          </button>
        </div>

        {advOpen ? (
          <div className="mt-4 space-y-3 border-t border-white/[0.08] pt-4">
            <p className="text-[12px] text-white/50">
              Saved only in this browser. Technical key: <span className="font-mono text-[11px]">hww.localRuntimeBase</span>{" "}
              in <span className="font-mono text-[11px]">localStorage</span>. Not a build-time or cloud secret.
            </p>
            <label className="block text-[12px] font-medium text-white/70" htmlFor="hww-local-runtime-url">
              Local runtime URL
            </label>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <input
                id="hww-local-runtime-url"
                value={localUrl}
                onChange={(e) => setLocalUrl(e.target.value)}
                placeholder={LOCAL_RUNTIME_SUGGESTIONS[0]}
                className="hww-input min-w-0 flex-1 rounded-lg font-mono text-[12px]"
                autoComplete="off"
                spellCheck={false}
              />
              <div className="flex shrink-0 gap-2">
                <Button type="button" size="sm" variant="secondary" className="border border-white/10" onClick={handleSave}>
                  Save
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => void handleTest()}
                  disabled={testing || !localUrl.trim()}
                  title={!localUrl.trim() ? "Enter a URL (e.g. http://127.0.0.1:8001)" : undefined}
                >
                  {testing ? "Testing…" : "Test connection"}
                </Button>
              </div>
            </div>

            <div className="rounded-lg border border-white/[0.06] bg-black/20 px-3 py-2.5 text-[12px] text-white/55">
              <p className="text-[11px] font-medium uppercase tracking-wide text-white/35">Filesystem root (API env)</p>
              <p className="mt-1 font-mono text-[11px] text-emerald-200/80">HAM_WORKSPACE_ROOT=&lt;path on this machine&gt;</p>
              <p className="mt-2 text-[11px] text-white/40">
                Path the local Python process reads (not the URL above). Run{" "}
                <span className="font-mono text-[10px] text-white/50">uvicorn src.api.server:app --host 127.0.0.1 --port 8001</span> on
                this machine. If a public Vercel page cannot reach loopback, set{" "}
                <span className="font-mono text-[10px]">HAM_CORS_ORIGINS</span> on that process to include this site, or
                use <span className="font-mono text-[10px]">HAM_CORS_ORIGIN_REGEX</span> for preview deploys.
              </p>
            </div>

            {lastTest ? (
              <div
                className={`rounded-lg border px-3 py-2.5 text-[12px] ${
                  lastTest.ok
                    ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-100/90"
                    : "border-amber-500/30 bg-amber-500/10 text-amber-100/90"
                }`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{statusLabel}</span>
                  <span className="text-[11px] opacity-90">{lastTest.message}</span>
                </div>
                {lastTest.testedUrl ? (
                  <p className="mt-1.5 break-all font-mono text-[10px] text-white/50">{lastTest.testedUrl}</p>
                ) : null}
                {lastTest.health ? (
                  <p className="mt-1 text-[10px] text-white/45">
                    HAM_WORKSPACE_ROOT:{" "}
                    {lastTest.health.workspaceRootConfigured
                      ? lastTest.health.workspaceRootPath || "set"
                      : "not set (sandbox fallback may apply)"}
                    {lastTest.health.broadFilesystemAccess ? " · broad path" : ""} · features:{" "}
                    {(lastTest.health.features || []).join(", ") || "—"}
                  </p>
                ) : null}
              </div>
            ) : (
              <p className="text-[11px] text-white/35">Test uses /api/workspace/health on the URL above.</p>
            )}
          </div>
        ) : null}
      </section>

      <section className="hww-set-card rounded-2xl border border-white/[0.08] bg-white/[0.02] p-5 shadow-none md:p-6">
        <h3 className="text-sm font-semibold text-white/90">Environment</h3>
        <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-white/40">
          Variable names the API process can read (read-only; same idea as a repo{" "}
          <span className="font-mono text-white/45">.env</span> in upstream docs). Values are not shown here.
        </p>
        <div className="mt-4">
          <EnvironmentReadonlyPanel variant="workspace" />
        </div>
      </section>
    </div>
  );
}
