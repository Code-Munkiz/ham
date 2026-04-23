import * as React from "react";
import { X } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  cloudAgentIdFromLaunchResponse,
  launchCursorAgent,
  shortenHamApiErrorMessage,
} from "@/lib/ham/api";
import { buildManagedCloudAgentPrompt } from "@/lib/ham/managedCloudAgent";
import type { CloudMissionHandling } from "@/lib/ham/types";

export type RecentCloudMission = { id: string; label?: string; t: number };

export interface CloudAgentLaunchModalProps {
  open: boolean;
  onClose: () => void;
  /** Syncs radio state when the dialog opens (parent `cloudMissionHandling`). */
  defaultMissionHandling: CloudMissionHandling;
  /** Single activation path: set active mission id + persist + recent (parent owns SSOT). */
  onActivateMission: (
    id: string,
    opts: {
      label?: string;
      mission_handling: CloudMissionHandling;
      managedSplit?: { kind: "new_launch" } | { kind: "existing" };
    },
  ) => void;
  recentMissions: RecentCloudMission[];
  onRemoveRecent: (id: string) => void;
  mountDefaults?: { repository: string; ref: string };
}

export function CloudAgentLaunchModal({
  open,
  onClose,
  defaultMissionHandling,
  onActivateMission,
  recentMissions,
  onRemoveRecent,
  mountDefaults,
}: CloudAgentLaunchModalProps) {
  const [missionHandling, setMissionHandling] = React.useState<CloudMissionHandling>("direct");
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
  /** Invalid attach (e.g. user previously pasted a repo URL as an "agent id"). */
  const [attachErr, setAttachErr] = React.useState<string | null>(null);

  const sortedRecent = React.useMemo(
    () => [...recentMissions].sort((a, b) => b.t - a.t),
    [recentMissions],
  );

  React.useEffect(() => {
    if (!open) return;
    setLaunchErr(null);
    setAttachErr(null);
    setMissionHandling(defaultMissionHandling);
    setManualId("");
    setPromptText("");
    setRepository(mountDefaults?.repository?.trim() ?? "");
    setRef((mountDefaults?.ref ?? "").trim() || "main");
    setModel("default");
    setBranchName("");
    setAutoCreatePr(false);
    setAdvancedOpen(false);
  }, [open, mountDefaults?.repository, mountDefaults?.ref, defaultMissionHandling]);

  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const attachReasonIfInvalid = (raw: string): string | null => {
    const t = raw.trim();
    if (!t) return "Empty id.";
    if (/^https?:\/\//i.test(t)) {
      return "That is a URL, not a Cursor agent id. Use Start new mission with the repo URL, or paste an id like bc_…";
    }
    if (/\bgithub\.com\b/i.test(t) && !t.startsWith("bc_")) {
      return "That looks like a GitHub path, not an agent id. Remove this row or launch a new mission below with the repository field.";
    }
    return null;
  };

  const attach = (id: string) => {
    const why = attachReasonIfInvalid(id);
    if (why) {
      setAttachErr(why);
      return;
    }
    setAttachErr(null);
    onActivateMission(id.trim(), {
      mission_handling: missionHandling,
      ...(missionHandling === "managed" ? { managedSplit: { kind: "existing" as const } } : {}),
    });
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
      const promptToSend =
        missionHandling === "managed"
          ? buildManagedCloudAgentPrompt({
              userPrompt: p,
              repository: r,
              ref: ref.trim() || undefined,
            })
          : p;
      const payload = await launchCursorAgent({
        prompt_text: promptToSend,
        repository: r,
        ref: ref.trim() || undefined,
        model: model.trim() || "default",
        auto_create_pr: autoCreatePr,
        branch_name: branchName.trim() || undefined,
        mission_handling: missionHandling,
      });
      const newId = cloudAgentIdFromLaunchResponse(payload);
      if (!newId) {
        setLaunchErr(shortenHamApiErrorMessage("Launch succeeded but response had no agent id.", 100));
        return;
      }
      const shortRepo = r.replace(/^https?:\/\/github\.com\//i, "").slice(0, 48);
      onActivateMission(newId, {
        label: shortRepo || undefined,
        mission_handling: missionHandling,
        ...(missionHandling === "managed" ? { managedSplit: { kind: "new_launch" as const } } : {}),
      });
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
          <section className="space-y-2" aria-labelledby="mission-handling-heading">
            <div id="mission-handling-heading" className="text-[9px] font-black text-white/30 uppercase tracking-widest">
              Mission handling
            </div>
            <p className="text-[9px] text-white/30 leading-snug">
              Direct = launch or attach only. Managed = HAM can plan, track, and summarize around this mission as those
              features ship.
            </p>
            <div className="flex flex-wrap gap-2">
              <label
                className={cn(
                  "flex-1 min-w-[120px] cursor-pointer rounded-lg border px-3 py-2 text-[10px] font-bold transition-colors",
                  missionHandling === "direct"
                    ? "border-[#00E5FF]/50 bg-[#00E5FF]/8 text-white"
                    : "border-white/10 bg-black/40 text-white/50 hover:border-white/20",
                )}
              >
                <input
                  type="radio"
                  className="sr-only"
                  name="mission-handling"
                  checked={missionHandling === "direct"}
                  onChange={() => setMissionHandling("direct")}
                />
                Direct
              </label>
              <label
                className={cn(
                  "flex-1 min-w-[120px] cursor-pointer rounded-lg border px-3 py-2 text-[10px] font-bold transition-colors",
                  missionHandling === "managed"
                    ? "border-[#00E5FF]/50 bg-[#00E5FF]/8 text-white"
                    : "border-white/10 bg-black/40 text-white/50 hover:border-white/20",
                )}
              >
                <input
                  type="radio"
                  className="sr-only"
                  name="mission-handling"
                  checked={missionHandling === "managed"}
                  onChange={() => setMissionHandling("managed")}
                />
                Managed by HAM
              </label>
            </div>
          </section>

          <section className="space-y-2">
            <div className="text-[9px] font-black text-white/30 uppercase tracking-widest">Attach existing</div>
            <p className="text-[9px] text-white/35 leading-snug">
              Re-attach a past <span className="text-white/55">Cursor Cloud Agent id</span> (usually <span className="font-mono text-white/50">bc_…</span>). To
              target a GitHub repo, use <span className="text-white/55">Start new mission</span> — not this list.
            </p>
            {attachErr ? (
              <p className="text-[10px] font-bold text-amber-500/90 uppercase tracking-wide whitespace-pre-wrap">
                {attachErr}
              </p>
            ) : null}
            {sortedRecent.length === 0 ? (
              <p className="text-[10px] text-white/35">No saved mission ids yet — start a new mission below.</p>
            ) : (
              <ul className="space-y-2 max-h-40 overflow-y-auto">
                {sortedRecent.map((m) => (
                  <li
                    key={`${m.id}-${m.t}`}
                    className="flex items-center justify-between gap-2 border border-white/10 rounded-lg px-3 py-2"
                  >
                    <span className="min-w-0 flex flex-col gap-0.5">
                      <span className="text-[10px] font-mono text-[#00E5FF] truncate" title={m.id}>
                        {m.id}
                      </span>
                      {m.label ? (
                        <span className="text-[9px] text-white/40 truncate" title={m.label}>
                          {m.label}
                        </span>
                      ) : null}
                    </span>
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
