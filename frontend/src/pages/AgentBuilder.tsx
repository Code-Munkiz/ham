/**
 * HAM Agent Builder — project-scoped assistant profiles (not Hermes runtime profiles).
 * Skills attach Hermes **catalog** ids; `/api/chat` uses them as context-only guidance when `project_id` is sent (not tool execution).
 */
import * as React from "react";
import {
  AlertTriangle,
  Check,
  Loader2,
  Plus,
  Save,
  Star,
  Trash2,
  Upload,
  User,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { HermesSkillPicker } from "@/components/agent-builder/HermesSkillPicker";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";
import { Input } from "@/components/ui/input";
import { imageFileToAvatarDataUrl } from "@/lib/ham/imageAvatar";
import {
  ensureProjectIdForWorkspaceRoot,
  fetchContextEngine,
  fetchHermesSkillsCatalog,
  fetchProjectAgents,
  fetchSettingsWriteStatus,
  postSettingsApply,
  postSettingsPreview,
  registerHamProject,
  type HamAgentProfile,
  type HamAgentsConfig,
  type HamSettingsPreviewResponse,
  type HermesSkillCatalogEntry,
} from "@/lib/ham/api";

function cloneAgents(c: HamAgentsConfig): HamAgentsConfig {
  return JSON.parse(JSON.stringify(c)) as HamAgentsConfig;
}

async function fetchAgentsResilient(projectId: string, cwd: string): Promise<HamAgentsConfig> {
  try {
    return await fetchProjectAgents(projectId);
  } catch (e) {
    const msg = e instanceof Error ? e.message : "";
    if (!msg.includes("PROJECT_NOT_FOUND")) {
      throw e;
    }
    const norm = cwd.replace(/\/$/, "");
    await registerHamProject({
      name: norm.split("/").filter(Boolean).pop() || "workspace",
      root: norm,
      description: "Re-registered from Agent Builder (registry miss on prior request).",
    });
    return await fetchProjectAgents(projectId);
  }
}

const labelClass =
  "text-[8px] font-black text-white/20 uppercase tracking-[0.2em] mb-1.5 block";

function newProfileId(name: string, existing: Set<string>): string {
  const base =
    name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ".")
      .replace(/^\.+|\.+$/g, "")
      .slice(0, 40) || "agent";
  let id = `custom.${base}`;
  let n = 0;
  while (existing.has(id)) {
    n += 1;
    id = `custom.${base}.${n}`;
  }
  return id;
}

export default function AgentBuilder() {
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);
  const [projectId, setProjectId] = React.useState<string | null>(null);
  const [catalog, setCatalog] = React.useState<HermesSkillCatalogEntry[]>([]);
  const [draft, setDraft] = React.useState<HamAgentsConfig | null>(null);
  const [baseline, setBaseline] = React.useState<HamAgentsConfig | null>(null);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [writesEnabled, setWritesEnabled] = React.useState<boolean | null>(null);
  const [writeToken, setWriteToken] = React.useState("");
  const [preview, setPreview] = React.useState<HamSettingsPreviewResponse | null>(null);
  const [busy, setBusy] = React.useState<"preview" | "apply" | null>(null);
  const avatarInputRef = React.useRef<HTMLInputElement>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setErr(null);
    setPreview(null);
    try {
      const ctx = await fetchContextEngine();
      const pid = await ensureProjectIdForWorkspaceRoot(ctx.cwd);
      const [agents, cat, ws] = await Promise.all([
        fetchAgentsResilient(pid, ctx.cwd),
        fetchHermesSkillsCatalog(),
        fetchSettingsWriteStatus(),
      ]);
      setProjectId(pid);
      setCatalog(cat.entries);
      const cl = cloneAgents(agents);
      setDraft(cl);
      setBaseline(cl);
      setSelectedId((prev) => {
        if (prev && cl.profiles.some((p) => p.id === prev)) return prev;
        return cl.primary_agent_id;
      });
      setWritesEnabled(ws.writes_enabled);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load");
      setDraft(null);
      setBaseline(null);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  const selected = draft?.profiles.find((p) => p.id === selectedId) ?? null;

  const onAvatarFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f || !selectedId) return;
    try {
      const dataUrl = await imageFileToAvatarDataUrl(f);
      if (!draft) return;
      setDraft({
        ...draft,
        profiles: draft.profiles.map((p) =>
          p.id === selectedId ? { ...p, avatar_url: dataUrl } : p,
        ),
      });
      setPreview(null);
      toast.success("Avatar updated in draft — preview & save to persist.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not read image");
    }
  };

  const clearAvatar = () => {
    if (!draft || !selectedId) return;
    setDraft({
      ...draft,
      profiles: draft.profiles.map((p) =>
        p.id === selectedId ? { ...p, avatar_url: "" } : p,
      ),
    });
    setPreview(null);
    toast.message("Avatar cleared in draft.");
  };

  const updateSelected = (patch: Partial<HamAgentProfile>) => {
    if (!draft || !selectedId) return;
    setDraft({
      ...draft,
      profiles: draft.profiles.map((p) => (p.id === selectedId ? { ...p, ...patch } : p)),
    });
    setPreview(null);
  };

  const setPrimary = (id: string) => {
    if (!draft) return;
    if (!draft.profiles.some((p) => p.id === id)) return;
    setDraft({ ...draft, primary_agent_id: id });
    setPreview(null);
  };

  const addProfile = () => {
    if (!draft) return;
    const existing = new Set(draft.profiles.map((p) => p.id));
    const id = newProfileId("Specialist", existing);
    const p: HamAgentProfile = {
      id,
      name: "New specialist",
      description: "",
      skills: [],
      enabled: true,
      avatar_url: "",
    };
    setDraft({ ...draft, profiles: [...draft.profiles, p] });
    setSelectedId(id);
    setPreview(null);
    toast.success("Profile added — edit details and save.");
  };

  const deleteProfile = (id: string) => {
    if (!draft) return;
    if (draft.profiles.length <= 1) {
      toast.error("Keep at least one HAM agent profile.");
      return;
    }
    if (draft.primary_agent_id === id) {
      toast.error("Choose another primary agent before deleting this profile.");
      return;
    }
    const nextProfiles = draft.profiles.filter((p) => p.id !== id);
    setDraft({ ...draft, profiles: nextProfiles });
    if (selectedId === id) {
      setSelectedId(draft.primary_agent_id);
    }
    setPreview(null);
    toast.message("Profile removed from draft — save to persist.");
  };

  const dirty =
    draft && baseline ? JSON.stringify(draft) !== JSON.stringify(baseline) : false;

  const runPreview = async () => {
    if (!projectId || !draft) return;
    const ids = new Set(draft.profiles.map((p) => p.id));
    if (ids.size !== draft.profiles.length) {
      toast.error("Duplicate profile ids are not allowed.");
      return;
    }
    if (!ids.has(draft.primary_agent_id)) {
      toast.error("Primary agent must match a profile id.");
      return;
    }
    for (const p of draft.profiles) {
      if (!p.name.trim()) {
        toast.error(`Profile ${p.id} needs a name.`);
        return;
      }
    }
    setBusy("preview");
    setPreview(null);
    try {
      const pr = await postSettingsPreview(projectId, { agents: draft });
      setPreview(pr);
      if (pr.diff.length === 0) {
        toast.message("No effective change.");
      } else {
        toast.success("Preview ready.");
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Preview failed");
    } finally {
      setBusy(null);
    }
  };

  const runApply = async () => {
    if (!projectId || !preview) return;
    const tok = writeToken.trim();
    if (!tok) {
      toast.error("Paste HAM_SETTINGS_WRITE_TOKEN to apply.");
      return;
    }
    if (!draft) return;
    setBusy("apply");
    try {
      await postSettingsApply(projectId, { agents: draft }, preview.base_revision, tok);
      toast.success("Saved to .ham/settings.json");
      setBaseline(cloneAgents(draft));
      setPreview(null);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Apply failed");
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center bg-[#050505] text-white/40 gap-2 text-sm font-bold">
        <Loader2 className="h-5 w-5 animate-spin text-[#FF6B00]" />
        Loading agent builder…
      </div>
    );
  }

  if (err || !draft) {
    return (
      <div className="h-full flex flex-col items-center justify-center bg-[#050505] p-8 text-center gap-4">
        <AlertTriangle className="h-10 w-10 text-amber-500/80" />
        <p className="text-sm font-bold text-white/60 max-w-md">{err ?? "No data"}</p>
        <button
          type="button"
          onClick={() => void load()}
          className="px-4 py-2 rounded border border-white/10 text-[11px] font-black uppercase tracking-widest text-white/70 hover:bg-white/5"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-[#050505] text-white overflow-hidden">
      <input
        ref={avatarInputRef}
        type="file"
        accept="image/png,image/jpeg,image/jpg,image/webp,image/gif"
        className="hidden"
        onChange={(e) => void onAvatarFile(e)}
      />

      <div className="h-10 flex items-center px-4 border-b border-white/5 bg-black/40 justify-between shrink-0">
        <span className="text-[9px] font-black text-white/30 uppercase tracking-[0.35em] italic leading-none">
          Configuration · HAM agent profiles
        </span>
        <Save className="h-2.5 w-2.5 text-[#FF6B00]/60" />
      </div>

      <div className="shrink-0 border-b border-white/5 w-full px-4 py-4 md:px-6">
        <div className="flex flex-col xl:flex-row xl:items-end justify-between gap-4 w-full">
          <div className="space-y-2 min-w-0">
            <h1 className="text-2xl md:text-3xl font-black italic uppercase tracking-tighter text-white leading-none">
              Agent <span className="text-[#FF6B00] not-italic">profiles</span>
            </h1>
            <p className="text-[10px] font-bold text-white/35 uppercase tracking-widest max-w-2xl leading-relaxed">
              Full-width setup (like the droid panel, without the narrow sidebar). The primary profile’s
              avatar appears in Chat. Skills stay catalog ids; chat uses them as context-only guidance.
            </p>
          </div>
          <div className="flex flex-wrap gap-2 shrink-0">
            <button
              type="button"
              onClick={addProfile}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-white/10 bg-white/[0.04] text-[10px] font-black uppercase tracking-widest hover:border-[#FF6B00]/40 transition-colors"
            >
              <Plus className="h-4 w-4" />
              New profile
            </button>
            <button
              type="button"
              disabled={!dirty || busy !== null}
              onClick={() => void runPreview()}
              className={cn(
                "flex items-center gap-2 px-4 py-2.5 rounded-lg text-[10px] font-black uppercase tracking-widest",
                "bg-[#FF6B00]/20 border border-[#FF6B00]/40 text-[#FF6B00] hover:bg-[#FF6B00]/30 disabled:opacity-30",
              )}
            >
              {busy === "preview" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Preview save
            </button>
          </div>
        </div>
        {writesEnabled === false && (
          <p className="mt-3 text-[10px] font-bold text-amber-500/80 uppercase tracking-widest">
            Apply is disabled on this server (HAM_SETTINGS_WRITE_TOKEN). Preview still works.
          </p>
        )}

        <div className="mt-4 flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
          {draft.profiles.map((p) => {
            const isPri = draft.primary_agent_id === p.id;
            const active = selectedId === p.id;
            const av = p.avatar_url?.trim();
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => setSelectedId(p.id)}
                className={cn(
                  "flex items-center gap-2 shrink-0 rounded-lg px-3 py-2 border transition-colors min-w-[8rem] max-w-[14rem]",
                  active
                    ? "border-[#FF6B00]/50 bg-[#FF6B00]/10"
                    : "border-white/10 bg-white/[0.02] hover:border-white/20",
                )}
              >
                <div className="h-9 w-9 rounded-md border border-white/10 bg-black/40 overflow-hidden flex items-center justify-center shrink-0">
                  {av ? (
                    <img src={av} alt="" className="h-full w-full object-cover" />
                  ) : (
                    <User className="h-4 w-4 text-white/25" />
                  )}
                </div>
                <div className="min-w-0 text-left">
                  <div className="flex items-center gap-1">
                    {isPri && (
                      <Star className="h-2.5 w-2.5 text-[#FF6B00] shrink-0 fill-[#FF6B00]/30" />
                    )}
                    <span className="text-[10px] font-black uppercase tracking-tight truncate text-white">
                      {p.name || p.id}
                    </span>
                  </div>
                  <div className="text-[8px] font-mono text-white/25 truncate">{p.id}</div>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto scrollbar-hide w-full">
        <div className="w-full max-w-[1600px] mx-auto px-4 md:px-8 py-6 space-y-6">
          {selected ? (
            <>
              <div className="flex flex-wrap items-start justify-end gap-2">
                {draft.primary_agent_id !== selected.id && (
                  <button
                    type="button"
                    onClick={() => setPrimary(selected.id)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-[#FF6B00]/30 text-[9px] font-black uppercase tracking-widest text-[#FF6B00] hover:bg-[#FF6B00]/10"
                  >
                    <Star className="h-3 w-3" />
                    Set primary
                  </button>
                )}
                {draft.primary_agent_id === selected.id && (
                  <span className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-white/10 text-[9px] font-black uppercase tracking-widest text-white/40">
                    <Check className="h-3 w-3 text-emerald-500" />
                    Primary (shown in chat)
                  </span>
                )}
                {draft.profiles.length > 1 && draft.primary_agent_id !== selected.id && (
                  <button
                    type="button"
                    onClick={() => deleteProfile(selected.id)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-red-500/30 text-[9px] font-black uppercase tracking-widest text-red-400/90 hover:bg-red-500/10"
                  >
                    <Trash2 className="h-3 w-3" />
                    Delete
                  </button>
                )}
              </div>
              <p className="text-[9px] font-mono text-white/25 -mt-2">{selected.id}</p>

              <CollapsibleSection title="Identity" defaultOpen>
                <div className="space-y-4 pt-2">
                  <div className="flex flex-col sm:flex-row sm:items-start gap-6">
                    <div className="flex flex-col items-center gap-3 shrink-0">
                      <div className="relative h-28 w-28 rounded-xl border border-white/10 bg-white/[0.03] overflow-hidden flex items-center justify-center shadow-[0_0_40px_rgba(255,107,0,0.08)]">
                        {selected.avatar_url?.trim() ? (
                          <img
                            src={selected.avatar_url.trim()}
                            alt=""
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          <User className="h-12 w-12 text-white/15" />
                        )}
                      </div>
                      <div className="flex flex-wrap justify-center gap-2">
                        <button
                          type="button"
                          onClick={() => avatarInputRef.current?.click()}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-white/15 bg-black/40 text-[9px] font-black uppercase tracking-widest text-white/70 hover:border-[#FF6B00]/40"
                        >
                          <Upload className="h-3 w-3" />
                          Upload image
                        </button>
                        <button
                          type="button"
                          disabled={!selected.avatar_url?.trim()}
                          onClick={clearAvatar}
                          className="px-3 py-1.5 rounded border border-white/10 text-[9px] font-black uppercase tracking-widest text-white/40 hover:text-white/60 disabled:opacity-25"
                        >
                          Clear
                        </button>
                      </div>
                      <p className="text-[8px] font-bold text-white/25 uppercase tracking-widest text-center max-w-[11rem] leading-relaxed">
                        JPEG after resize (~256px). Saved in settings when you apply.
                      </p>
                    </div>
                    <div className="flex-1 space-y-4 min-w-0">
                      <div className="grid gap-4 md:grid-cols-2">
                        <label className="space-y-1.5 block">
                          <span className={labelClass}>Name</span>
                          <Input
                            value={selected.name}
                            onChange={(e) => updateSelected({ name: e.target.value })}
                            className="h-10 bg-black/40 border-white/10 text-[12px] font-bold text-white"
                          />
                        </label>
                        <label className="space-y-1.5 flex items-center gap-3 md:pt-7">
                          <input
                            type="checkbox"
                            checked={selected.enabled}
                            onChange={(e) => updateSelected({ enabled: e.target.checked })}
                            className="rounded border-white/20 bg-black"
                          />
                          <span className="text-[10px] font-black text-white/50 uppercase tracking-widest">
                            Enabled
                          </span>
                        </label>
                      </div>
                      <label className="space-y-1.5 block">
                        <span className={labelClass}>Description</span>
                        <textarea
                          value={selected.description ?? ""}
                          onChange={(e) => updateSelected({ description: e.target.value })}
                          rows={4}
                          className="w-full rounded-md border border-white/10 bg-black/40 px-3 py-2 text-[12px] font-bold text-white placeholder:text-white/20 resize-none"
                        />
                      </label>
                    </div>
                  </div>
                </div>
              </CollapsibleSection>

              <CollapsibleSection title="Hermes runtime skills" count={selected.skills.length}>
                <div className="space-y-3 pt-2">
                  <p className="text-[10px] font-bold text-white/30 leading-relaxed">
                    Catalog ids only — they do not install or invoke tools from this UI.
                  </p>
                  <HermesSkillPicker
                    entries={catalog}
                    selectedIds={selected.skills}
                    onChange={(ids) => updateSelected({ skills: ids })}
                  />
                </div>
              </CollapsibleSection>
            </>
          ) : (
            <p className="text-sm text-white/40 font-bold">Select a profile above</p>
          )}

          {preview && (
            <div className="rounded-xl border border-white/10 bg-black/40 p-4 space-y-3">
              <h3 className="text-[10px] font-black uppercase tracking-widest text-[#FF6B00]">
                Preview diff
              </h3>
              <ul className="space-y-2 max-h-48 overflow-y-auto text-[10px] font-mono text-white/50">
                {preview.diff.map((row, i) => (
                  <li key={i} className="border-b border-white/5 pb-2">
                    <span className="text-[#FF6B00]/80">{row.path}</span>
                  </li>
                ))}
              </ul>
              {preview.warnings.length > 0 && (
                <div className="text-[10px] font-bold text-amber-500/90 space-y-1">
                  {preview.warnings.map((w) => (
                    <p key={w}>{w}</p>
                  ))}
                </div>
              )}
              <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
                <label className="flex-1 space-y-1">
                  <span className="text-[9px] font-black text-white/40 uppercase tracking-widest">
                    HAM_SETTINGS_WRITE_TOKEN
                  </span>
                  <Input
                    type="password"
                    autoComplete="off"
                    value={writeToken}
                    onChange={(e) => setWriteToken(e.target.value)}
                    className="h-9 bg-black/60 border-white/10 text-[11px] font-mono text-white"
                  />
                </label>
                <button
                  type="button"
                  disabled={writesEnabled === false || busy !== null}
                  onClick={() => void runApply()}
                  className={cn(
                    "px-4 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest",
                    "bg-emerald-600/90 text-black hover:bg-emerald-500 disabled:opacity-30",
                  )}
                >
                  {busy === "apply" ? (
                    <Loader2 className="h-4 w-4 animate-spin inline" />
                  ) : (
                    "Apply"
                  )}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
