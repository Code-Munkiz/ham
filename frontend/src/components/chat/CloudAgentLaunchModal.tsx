import * as React from "react";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  cloudAgentIdFromLaunchResponse,
  launchCursorAgent,
  shortenHamApiErrorMessage,
} from "@/lib/ham/api";

export type RecentCloudMission = { id: string; label?: string; t: number };

export interface CloudAgentLaunchModalProps {
  open: boolean;
  onClose: () => void;
  /** Single activation path: set active mission id + persist + recent (parent owns SSOT). */
  onActivateMission: (id: string, label?: string) => void;
  recentMissions: RecentCloudMission[];
  onRemoveRecent: (id: string) => void;
  mountDefaults?: { repository: string; ref: string };
}

export function CloudAgentLaunchModal({
  open,
  onClose,
  onActivateMission,
  recentMissions,
  onRemoveRecent,
  mountDefaults,
}: CloudAgentLaunchModalProps) {
  const [manualId, setManualId] = React.useState("");
  const [promptText, setPromptText] = React.useState("");
  const [repository, setRepository] = React.useState("");
  const [ref, setRef] = React.useState("");
  const [model, setModel] = React.useState("default");
  const [branchName, setBranchName] = React.useState("");
  const [autoCreatePr, setAutoCreatePr] = React.useState(false);
  const [advancedOpen, setAdvancedOpen] = React.useState(false);
  const [launchBusy, setLaunchBusy] = React.useState(false);
  const [launchErr, setLaunchErr] = React.useState<string | null>(null);

  const sortedRecent = React.useMemo(
    () => [...recentMissions].sort((a, b) => b.t - a.t),
    [recentMissions],
  );

  React.useEffect(() => {
    if (!open) return;
    setLaunchErr(null);
    setManualId("");
    setPromptText("");
    setRepository(mountDefaults?.repository?.trim() ?? "");
    setRef((mountDefaults?.ref ?? "").trim() || "main");
    setModel("default");
    setBranchName("");
    setAutoCreatePr(false);
    setAdvancedOpen(false);
  }, [open, mountDefaults?.repository, mountDefaults?.ref]);

  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const attach = (id: string) => {
    const t = id.trim();
    if (!t) return;
    onActivateMission(t);
    onClose();
  };

  const onSubmitLaunch = async (e: React.FormEvent) => {
    e.preventDefault();
    setLaunchErr(null);
    const p = promptText.trim();
    const r = repository.trim();
    if (!p || !r) {
      setLaunchErr(shortenHamApiErrorMessage("Add a prompt and repository URL.", 80));
      return;
    }
    setLaunchBusy(true);
    try {
      const payload = await launchCursorAgent({
        prompt_text: p,
        repository: r,
        ref: ref.trim() || undefined,
        model: model.trim() || "default",
        auto_create_pr: autoCreatePr,
        branch_name: branchName.trim() || undefined,
      });
      const newId = cloudAgentIdFromLaunchResponse(payload);
      if (!newId) {
        setLaunchErr(shortenHamApiErrorMessage("Launch succeeded but response had no agent id.", 100));
        return;
      }
      const shortRepo = r.replace(/^https?:\/\/github\.com\//i, "").slice(0, 48);
      onActivateMission(newId, shortRepo || undefined);
      onClose();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Launch failed.";
      setLaunchErr(shortenHamApiErrorMessage(msg, 120));
    } finally {
      setLaunchBusy(false);
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[300] flex items-center justify-center p-4 bg-black/70 backdrop-blur-md"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="cloud-agent-mission-title"
        className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl border border-white/10 bg-[#0a0a0a] shadow-2xl text-white"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
          <div>
            <h2 id="cloud-agent-mission-title" className="text-[11px] font-black uppercase tracking-[0.2em] text-white">
              Cloud Agent mission
            </h2>
            <p className="text-[9px] font-bold text-white/35 uppercase tracking-wider mt-1">
              Mission launch uses Cursor Cloud API (not dashboard chat).
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg text-white/40 hover:text-white hover:bg-white/5"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-4 space-y-6">
          <section className="space-y-2">
            <div className="text-[9px] font-black text-white/30 uppercase tracking-widest">Attach existing</div>
            {sortedRecent.length === 0 ? (
              <p className="text-[10px] text-white/35">No saved mission ids yet — start a new mission below.</p>
            ) : (
              <ul className="space-y-2 max-h-40 overflow-y-auto">
                {sortedRecent.map((m) => (
                  <li
                    key={m.id}
                    className="flex items-center justify-between gap-2 border border-white/10 rounded-lg px-3 py-2"
                  >
                    <span className="min-w-0 text-[10px] font-mono text-[#00E5FF] truncate">{m.id}</span>
                    <span className="flex items-center gap-2 shrink-0">
                      <button
                        type="button"
                        className="text-[9px] font-black uppercase tracking-wider text-white/40 hover:text-white"
                        onClick={() => onRemoveRecent(m.id)}
                      >
                        Remove
                      </button>
                      <button
                        type="button"
                        className="text-[9px] font-black uppercase tracking-wider text-[#FF6B00] hover:text-white"
                        onClick={() => attach(m.id)}
                      >
                        Select
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <div className="flex gap-2">
              <input
                value={manualId}
                onChange={(e) => setManualId(e.target.value)}
                placeholder="Paste agent id…"
                className="flex-1 min-w-0 rounded-lg border border-white/10 bg-black/50 px-3 py-2 text-[11px] font-mono text-white/90 outline-none focus:border-[#00E5FF]/40"
              />
              <button
                type="button"
                disabled={!manualId.trim()}
                onClick={() => attach(manualId)}
                className={cn(
                  "shrink-0 px-3 py-2 rounded-lg text-[9px] font-black uppercase tracking-widest border transition-colors",
                  manualId.trim()
                    ? "border-[#00E5FF]/50 text-[#00E5FF] hover:bg-[#00E5FF]/10"
                    : "border-white/10 text-white/25 cursor-not-allowed",
                )}
              >
                Attach
              </button>
            </div>
          </section>

          <section className="space-y-3 border-t border-white/5 pt-4">
            <div className="text-[9px] font-black text-white/30 uppercase tracking-widest">Start new mission</div>
            <form onSubmit={onSubmitLaunch} className="space-y-3">
              <textarea
                value={promptText}
                onChange={(e) => setPromptText(e.target.value)}
                placeholder="Prompt for the agent…"
                rows={4}
                className="w-full rounded-lg border border-white/10 bg-black/50 px-3 py-2 text-[11px] text-white/90 outline-none focus:border-[#FF6B00]/40 resize-y min-h-[88px]"
              />
              <input
                value={repository}
                onChange={(e) => setRepository(e.target.value)}
                placeholder="https://github.com/org/repo"
                className="w-full rounded-lg border border-white/10 bg-black/50 px-3 py-2 text-[11px] font-mono text-white/90 outline-none focus:border-[#FF6B00]/40"
              />
              <input
                value={ref}
                onChange={(e) => setRef(e.target.value)}
                placeholder="Branch or tag (optional)"
                className="w-full rounded-lg border border-white/10 bg-black/50 px-3 py-2 text-[11px] text-white/90 outline-none focus:border-[#FF6B00]/40"
              />
              <button
                type="button"
                onClick={() => setAdvancedOpen(!advancedOpen)}
                className="text-[9px] font-black uppercase tracking-widest text-white/40 hover:text-white/70"
              >
                {advancedOpen ? "− Hide" : "+"} advanced
              </button>
              {advancedOpen ? (
                <div className="space-y-2 pl-1 border-l border-white/10">
                  <input
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    placeholder='Model (default: "default")'
                    className="w-full rounded-lg border border-white/10 bg-black/50 px-3 py-2 text-[11px] text-white/90 outline-none"
                  />
                  <label className="flex items-center gap-2 text-[10px] font-bold text-white/50 uppercase tracking-wider">
                    <input
                      type="checkbox"
                      checked={autoCreatePr}
                      onChange={(e) => setAutoCreatePr(e.target.checked)}
                      className="rounded border-white/20"
                    />
                    Auto-create PR
                  </label>
                  <input
                    value={branchName}
                    onChange={(e) => setBranchName(e.target.value)}
                    placeholder="Target branch name (optional)"
                    className="w-full rounded-lg border border-white/10 bg-black/50 px-3 py-2 text-[11px] text-white/90 outline-none"
                  />
                </div>
              ) : null}
              {launchErr ? (
                <p className="text-[10px] font-bold text-amber-500/90 uppercase tracking-wide">{launchErr}</p>
              ) : null}
              <button
                type="submit"
                disabled={launchBusy || !promptText.trim() || !repository.trim()}
                className="w-full rounded-lg bg-[#FF6B00] py-2.5 text-[10px] font-black uppercase tracking-widest text-black hover:brightness-110 disabled:opacity-40 disabled:pointer-events-none"
              >
                {launchBusy ? "Launching…" : "Launch agent"}
              </button>
            </form>
          </section>
        </div>
      </div>
    </div>
  );
}
