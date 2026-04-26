/**
 * Lists Browser Operator proposals for the active session; Approve / Deny for pending only.
 */
import * as React from "react";
import { Loader2, RefreshCw } from "lucide-react";
import {
  approveBrowserProposal,
  denyBrowserProposal,
  listBrowserProposals,
  type BrowserActionProposal,
  type BrowserProposalState,
} from "@/lib/ham/api";
import { cn } from "@/lib/utils";

function stateLabel(state: BrowserProposalState, nowMs: number, expiresAt: string): string {
  if (state === "proposed") {
    const exp = Date.parse(expiresAt);
    if (!Number.isNaN(exp) && nowMs > exp) return "Expired";
    return "Pending proposal";
  }
  if (state === "approved") return "Approved / executing";
  if (state === "executed") return "Executed";
  if (state === "denied") return "Denied";
  if (state === "expired") return "Expired";
  if (state === "failed") return "Failed";
  return state;
}

function actionSummary(p: BrowserActionProposal): string {
  const a = p.action;
  switch (a.action_type) {
    case "browser.navigate":
      return `Open page ${a.url ?? ""}`.trim();
    case "browser.click_xy":
      return `Tap (${a.x ?? "?"}, ${a.y ?? "?"})`;
    case "browser.scroll":
      return `Scroll (${a.delta_x ?? 0}, ${a.delta_y ?? 0})`;
    case "browser.key":
      return `Key ${a.key ?? ""}`;
    case "browser.type":
      return `Type into ${a.selector ?? ""}`;
    case "browser.reset":
      return "Reset viewport";
    default:
      return a.action_type;
  }
}

export interface BrowserProposalTrayProps {
  sessionId: string | null;
  ownerKey: string;
  enabled: boolean;
  onAfterDecision?: () => void;
  pollMs?: number;
}

export function BrowserProposalTray({
  sessionId,
  ownerKey,
  enabled,
  onAfterDecision,
  pollMs = 2500,
}: BrowserProposalTrayProps) {
  const [items, setItems] = React.useState<BrowserActionProposal[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [listErr, setListErr] = React.useState<string | null>(null);
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [nowMs, setNowMs] = React.useState(() => Date.now());

  const loadProposals = React.useCallback(async () => {
    if (!sessionId || !enabled) {
      setItems([]);
      return;
    }
    setLoading(true);
    setListErr(null);
    try {
      const rows = await listBrowserProposals(sessionId, ownerKey, 32);
      setItems(rows);
    } catch (e: unknown) {
      setListErr(e instanceof Error ? e.message : "List failed.");
    } finally {
      setLoading(false);
    }
  }, [sessionId, ownerKey, enabled]);

  React.useEffect(() => {
    if (!sessionId || !enabled) {
      setItems([]);
      return;
    }
    void loadProposals();
    const t = window.setInterval(() => void loadProposals(), pollMs);
    return () => window.clearInterval(t);
  }, [sessionId, ownerKey, enabled, pollMs, loadProposals]);

  React.useEffect(() => {
    const t = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);

  async function onApprove(id: string) {
    setBusyId(id);
    try {
      await approveBrowserProposal(id, ownerKey);
      await loadProposals();
      onAfterDecision?.();
    } catch (e: unknown) {
      setListErr(e instanceof Error ? e.message : "Approve failed.");
    } finally {
      setBusyId(null);
    }
  }

  async function onDeny(id: string) {
    setBusyId(id);
    try {
      await denyBrowserProposal(id, ownerKey);
      await loadProposals();
      onAfterDecision?.();
    } catch (e: unknown) {
      setListErr(e instanceof Error ? e.message : "Deny failed.");
    } finally {
      setBusyId(null);
    }
  }

  if (!sessionId || !enabled) {
    return (
      <div className="rounded border border-white/10 bg-black/20 p-2 text-[9px] text-white/35">
        Proposals appear when an operator-mode session is active.
      </div>
    );
  }

  return (
    <div className="rounded border border-[#00E5FF]/20 bg-black/35 p-2 space-y-2 max-h-48 overflow-y-auto">
      <p className="text-[8px] text-white/40 leading-snug">
        Approving performs exactly one matching browser action for this session.
      </p>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[9px] font-black uppercase tracking-wider text-[#00E5FF]/80">
          Recent proposals
        </span>
        <button
          type="button"
          onClick={() => void loadProposals()}
          disabled={loading}
          className="inline-flex items-center gap-1 text-[8px] font-black uppercase text-white/45 hover:text-white/75 disabled:opacity-40"
          title="Refresh list"
        >
          <RefreshCw className={cn("h-3 w-3", loading && "animate-spin")} />
          Refresh
        </button>
      </div>

      {listErr ? <p className="text-[9px] text-amber-400/90 font-mono">{listErr}</p> : null}

      {items.length === 0 && !loading ? (
        <p className="text-[9px] text-white/35">No proposals yet. Propose an action below.</p>
      ) : null}

      <ul className="space-y-1.5">
        {items.map((p) => {
          const exp = Date.parse(p.expires_at);
          const expiredClient = p.state === "proposed" && !Number.isNaN(exp) && nowMs > exp;
          const label = stateLabel(p.state, nowMs, p.expires_at);
          const pending = p.state === "proposed" && !expiredClient;
          const ttlSec =
            !Number.isNaN(exp) && p.state === "proposed"
              ? Math.max(0, Math.ceil((exp - nowMs) / 1000))
              : null;

          return (
            <li
              key={p.proposal_id}
              className={cn(
                "rounded border px-2 py-1.5 text-[9px]",
                pending
                  ? "border-amber-500/35 bg-amber-500/5"
                  : expiredClient || p.state === "expired"
                    ? "border-white/5 bg-black/25 opacity-50"
                    : "border-white/10 bg-black/40 opacity-90",
              )}
            >
              <div className="font-mono text-[8px] text-white/40 truncate">{p.proposal_id.slice(0, 8)}…</div>
              <div className="text-white/70 mt-0.5">{actionSummary(p)}</div>
              <div className="text-[8px] mt-0.5 text-cyan-200/70">{label}</div>
              {ttlSec !== null && pending ? (
                <div className="text-[8px] text-white/35">Expires in ~{ttlSec}s</div>
              ) : null}
              {pending ? (
                <div className="flex gap-1 mt-1.5">
                  <button
                    type="button"
                    disabled={busyId !== null}
                    onClick={() => void onApprove(p.proposal_id)}
                    className="flex-1 text-[8px] font-black uppercase py-1 rounded bg-emerald-500/20 border border-emerald-500/40 text-emerald-200/90 hover:bg-emerald-500/30 disabled:opacity-40"
                  >
                    {busyId === p.proposal_id ? <Loader2 className="h-3 w-3 animate-spin mx-auto" /> : "Approve"}
                  </button>
                  <button
                    type="button"
                    disabled={busyId !== null}
                    onClick={() => void onDeny(p.proposal_id)}
                    className="flex-1 text-[8px] font-black uppercase py-1 rounded bg-white/5 border border-white/15 text-white/60 hover:bg-white/10 disabled:opacity-40"
                  >
                    Deny
                  </button>
                </div>
              ) : null}
              {p.state === "failed" && p.result_last_error ? (
                <p className="text-[8px] text-red-300/80 mt-1 font-mono truncate">{p.result_last_error}</p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
