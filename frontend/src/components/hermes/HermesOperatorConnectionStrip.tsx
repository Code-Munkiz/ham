import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Info, Link2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { isHamDesktopShell } from "@/lib/ham/desktopConfig";
import type { HermesGatewaySnapshot } from "@/lib/ham/hermesGateway";

type Props = {
  snapshot: HermesGatewaySnapshot;
  className?: string;
};

export function HermesOperatorConnectionStrip({ snapshot, className }: Props) {
  const oc = snapshot.operator_connection;
  if (!oc) return null;

  const { summary, snapshot_meta, guidance } = oc;
  const cliOk = summary.cli_probe === "ok";
  const http = summary.http_gateway_status;
  const httpOk = http === "healthy" || http === "degraded";
  const desktop = isHamDesktopShell();

  return (
    <div
      className={cn(
        "rounded-xl border border-white/[0.08] bg-[#0a0a0a] p-4 space-y-3 text-[10px] text-white/55",
        className,
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2 text-[9px] font-black uppercase tracking-[0.25em] text-white/35">
            <Link2 className="h-3.5 w-3.5 text-[#FF6B00]" />
            API-side operator connection
          </div>
          <p className="text-[8px] text-white/25 leading-snug pl-5">
            Read-only: Ham API host CLI + <span className="font-mono">HERMES_GATEWAY_*</span> probe.
            Desktop Hermes checks live under Settings.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-[9px] font-black uppercase tracking-widest">
          <Link to="/workspace/operations" className="text-[#FF6B00] hover:underline">
            Operations
          </Link>
          <span className="text-white/15">·</span>
          <Link
            to="/workspace/projects"
            className="text-white/45 hover:text-[#FF6B00] hover:underline"
          >
            Projects
          </Link>
          {desktop ? (
            <>
              <span className="text-white/15">·</span>
              <Link
                to="/workspace/settings?tab=desktop-bundle"
                className="text-white/45 hover:text-[#FF6B00] hover:underline"
              >
                Desktop + Hermes
              </Link>
            </>
          ) : null}
        </div>
      </div>

      <div className="grid sm:grid-cols-2 gap-3">
        <div className="rounded-lg border border-white/[0.06] bg-black/30 p-3 space-y-1">
          <p className="text-[8px] font-black uppercase tracking-widest text-white/25">
            Ham API — CLI probe
          </p>
          <div className="flex items-start gap-2">
            {cliOk ? (
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400/90 mt-0.5" />
            ) : (
              <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400/90 mt-0.5" />
            )}
            <div className="space-y-0.5 min-w-0">
              <p
                className={cn(
                  "font-mono text-[11px]",
                  cliOk ? "text-emerald-200/90" : "text-amber-200/85",
                )}
              >
                {summary.cli_probe}
                {summary.cli_version_line ? (
                  <span
                    className="block text-[10px] text-white/45 truncate"
                    title={summary.cli_version_line}
                  >
                    {summary.cli_version_line}
                  </span>
                ) : null}
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-white/[0.06] bg-black/30 p-3 space-y-1">
          <p className="text-[8px] font-black uppercase tracking-widest text-white/25">
            Ham API — HTTP gateway
          </p>
          <div className="flex items-start gap-2">
            {httpOk ? (
              <CheckCircle2
                className={cn(
                  "h-4 w-4 shrink-0 mt-0.5",
                  http === "healthy" ? "text-emerald-400/90" : "text-amber-400/80",
                )}
              />
            ) : (
              <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400/90 mt-0.5" />
            )}
            <p
              className={cn(
                "font-mono text-[11px]",
                http === "healthy" && "text-emerald-200/90",
                http === "degraded" && "text-amber-200/80",
                http === "not_configured" && "text-white/40",
                (http === "unreachable" || http === "auth_required" || http === "unknown") &&
                  "text-amber-200/85",
              )}
            >
              {http}
            </p>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[9px] text-white/40 font-mono">
        <span>
          <span className="text-white/25">chat_gateway_mode</span>{" "}
          {summary.ham_chat_gateway_mode ?? "—"}
        </span>
        <span className="text-white/15">|</span>
        <span title={snapshot_meta.captured_at}>
          snapshot {new Date(snapshot_meta.captured_at).toLocaleString()}
        </span>
        <span className="text-white/15">|</span>
        <span>
          TTL {Math.round(snapshot_meta.ttl_seconds)}s
          {snapshot_meta.has_degraded ? (
            <span className="text-amber-400/80 ml-1">
              · {snapshot_meta.degraded_capabilities_count} degraded
            </span>
          ) : null}
        </span>
      </div>

      <p className="flex items-start gap-2 text-[9px] text-white/35 leading-relaxed border-t border-white/[0.05] pt-2">
        <Info className="h-3.5 w-3.5 shrink-0 text-white/20 mt-0.5" />
        {guidance}
      </p>
    </div>
  );
}
