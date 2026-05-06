/**
 * Profiles surface: card grid + create / activate / rename / delete flow.
 */
import * as React from "react";
import { Check, Clock, Folder, Pencil, Sparkles, Trash2, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { workspaceProfilesAdapter, type WorkspaceProfile } from "../../adapters/profilesAdapter";
import { WorkspaceSurfaceStateCard } from "../../components/workspaceSurfaceChrome";

function fmtDate(ts: number): string {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(ts * 1000));
}

function ProfileStat({
  label,
  value,
  truncate,
}: {
  label: string;
  value: string | number;
  truncate?: boolean;
}) {
  return (
    <div className="flex flex-col items-center px-1 py-2.5">
      <div
        className={cn(
          "text-sm font-bold text-[var(--theme-text)]",
          truncate && "max-w-[72px] truncate text-xs",
        )}
      >
        {value}
      </div>
      <div className="mt-0.5 text-[10px] font-medium uppercase tracking-wider text-[var(--theme-muted)]">
        {label}
      </div>
    </div>
  );
}

export function WorkspaceProfilesScreen() {
  const [profiles, setProfiles] = React.useState<WorkspaceProfile[]>([]);
  const [defaultId, setDefaultId] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [createOpen, setCreateOpen] = React.useState(false);
  const [details, setDetails] = React.useState<WorkspaceProfile | null>(null);
  const [rename, setRename] = React.useState<WorkspaceProfile | null>(null);
  const [renameVal, setRenameVal] = React.useState("");

  const [newName, setNewName] = React.useState("");
  const [newEmoji, setNewEmoji] = React.useState("🤖");
  const [newModel, setNewModel] = React.useState("ham-local");
  const [newPrompt, setNewPrompt] = React.useState("");

  const load = React.useCallback(async () => {
    setLoading(true);
    setErr(null);
    const { profiles: list, defaultProfileId, bridge } = await workspaceProfilesAdapter.list();
    if (bridge.status === "pending") {
      setErr(bridge.detail);
      setProfiles([]);
      setDefaultId(null);
    } else {
      setProfiles(list);
      setDefaultId(defaultProfileId);
    }
    setLoading(false);
  }, []);

  React.useEffect(() => {
    void load();
  }, [load]);

  async function activate(id: string) {
    setBusy(id);
    const { error } = await workspaceProfilesAdapter.setDefault(id);
    setBusy(null);
    if (error) setErr(error);
    else void load();
  }

  async function del(p: WorkspaceProfile) {
    if (p.isDefault) {
      setErr("Cannot delete the active profile. Activate another first.");
      return;
    }
    if (!window.confirm(`Delete profile ${p.name}?`)) return;
    setBusy(p.id);
    const { error } = await workspaceProfilesAdapter.remove(p.id);
    setBusy(null);
    if (error) setErr(error);
    else void load();
  }

  async function doRename() {
    if (!rename) return;
    const n = renameVal.trim();
    if (!n) return;
    setBusy(rename.id);
    const { error } = await workspaceProfilesAdapter.patch(rename.id, { name: n });
    setBusy(null);
    if (error) setErr(error);
    else {
      setRename(null);
      void load();
    }
  }

  const activeName = profiles.find((p) => p.id === defaultId)?.name ?? "default";

  return (
    <div
      className="hws-root min-h-full overflow-y-auto"
      style={{ color: "var(--theme-text)", backgroundColor: "var(--theme-bg,transparent)" }}
    >
      <div className="mx-auto w-full max-w-[1200px] px-4 py-6 sm:px-6 lg:px-8">
        <div className="mb-4 flex flex-col gap-3 rounded-2xl border border-white/10 bg-black/20 p-4 shadow-sm md:flex-row md:items-center md:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <UserRound className="h-5 w-5" />
              <h1 className="text-lg font-semibold">Profiles</h1>
            </div>
            <p className="mt-1 text-sm text-[var(--theme-muted)]">
              Save model and system-prompt presets per agent persona. Activate one and it becomes
              the default for new chats.
            </p>
          </div>
          <Button
            onClick={() => {
              setCreateOpen(true);
              setNewName("");
              setNewEmoji("🤖");
              setNewModel("ham-local");
              setNewPrompt("");
            }}
            className="gap-2"
          >
            Create profile
          </Button>
        </div>

        {err && (
          <div className="mb-3">
            <WorkspaceSurfaceStateCard
              title="Profiles API unavailable"
              description="Profiles could not be loaded. Other routes may still work."
              tone="amber"
              technicalDetail={err}
              primaryAction={
                <Button type="button" size="sm" variant="secondary" onClick={() => void load()}>
                  Retry
                </Button>
              }
            />
          </div>
        )}

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {loading &&
            Array.from({ length: 3 }).map((_, i) => (
              <div
                key={i}
                className="h-80 animate-pulse rounded-2xl border border-white/10 bg-black/20"
              />
            ))}
          {!loading &&
            profiles.map((profile) => {
              const b = busy === profile.id;
              const isAct = profile.isDefault;
              return (
                <article
                  key={profile.id}
                  className="group relative overflow-hidden rounded-2xl border border-white/10 bg-black/25 shadow-sm"
                >
                  {isAct && (
                    <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-emerald-400 via-emerald-500 to-emerald-400" />
                  )}
                  <div className="flex flex-col items-center pt-6 pb-1">
                    <div className="relative">
                      <div
                        className={cn(
                          "rounded-full p-1",
                          isAct
                            ? "bg-gradient-to-br from-emerald-400 via-emerald-500 to-emerald-500 shadow-lg shadow-emerald-500/20"
                            : "bg-gradient-to-br from-white/20 to-white/5",
                        )}
                      >
                        <div
                          className={cn(
                            "flex size-20 items-center justify-center rounded-full border-2 text-3xl",
                            isAct ? "border-white bg-black/30" : "border-white/10 bg-black/40",
                          )}
                        >
                          {profile.emoji || "🤖"}
                        </div>
                      </div>
                      {isAct && (
                        <div className="absolute -bottom-0.5 left-1/2 flex -translate-x-1/2 items-center gap-1 rounded-full border-2 border-[var(--theme-bg)] bg-emerald-600 px-2 py-0.5">
                          <Check className="h-2.5 w-2.5 text-white" />
                          <span className="text-[9px] font-bold uppercase tracking-wider text-white">
                            Active
                          </span>
                        </div>
                      )}
                    </div>
                    <h2 className="mt-3 text-center text-lg font-bold">{profile.name}</h2>
                    <span className="mt-1 inline-block rounded-full bg-white/5 px-2.5 py-0.5 text-[11px] font-medium text-[var(--theme-muted)]">
                      {profile.model}
                    </span>
                  </div>
                  <div className="mx-4 mt-4 grid grid-cols-4 divide-x divide-white/10 rounded-xl border border-white/10 bg-black/30">
                    <ProfileStat label="Skills" value={0} />
                    <ProfileStat label="Sessions" value={0} />
                    <ProfileStat label="Model" value={profile.model || "—"} truncate />
                    <ProfileStat label="Env" value="—" />
                  </div>
                  <div className="mx-4 mt-3 flex items-center justify-center gap-1.5 text-xs text-[var(--theme-muted)]">
                    <Clock className="h-3 w-3" />
                    {fmtDate(profile.updatedAt)}
                  </div>
                  <div className="mt-4 flex border-t border-white/10 text-xs font-semibold">
                    <button
                      type="button"
                      onClick={() => void activate(profile.id)}
                      disabled={isAct || b}
                      className={cn(
                        "flex flex-1 items-center justify-center gap-1 border-r border-white/10 py-2.5",
                        isAct
                          ? "cursor-default text-white/20"
                          : "text-[var(--theme-text)] hover:bg-white/5",
                      )}
                    >
                      <Sparkles className="h-3.5 w-3.5" />
                      Activate
                    </button>
                    <button
                      type="button"
                      onClick={() => setDetails(profile)}
                      className="flex flex-1 items-center justify-center gap-1 border-r border-white/10 py-2.5 text-[var(--theme-text)] hover:bg-white/5"
                    >
                      <Folder className="h-3.5 w-3.5" />
                      Details
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setRename(profile);
                        setRenameVal(profile.name);
                      }}
                      className="flex flex-1 items-center justify-center gap-1 border-r border-white/10 py-2.5 text-[var(--theme-text)] hover:bg-white/5"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                      Rename
                    </button>
                    <button
                      type="button"
                      onClick={() => void del(profile)}
                      disabled={isAct || b}
                      className={cn(
                        "flex flex-1 items-center justify-center gap-1 py-2.5",
                        isAct ? "cursor-default text-white/20" : "text-red-400 hover:bg-red-950/20",
                      )}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      Delete
                    </button>
                  </div>
                </article>
              );
            })}
        </div>

        {!loading && profiles.length === 0 && !err && (
          <div className="mt-4 rounded-2xl border border-dashed border-white/15 bg-black/20 p-8 text-center">
            <p className="text-sm font-medium text-[var(--theme-text)]">No profiles yet</p>
            <p className="mt-2 text-sm text-[var(--theme-muted)]">
              Create a profile to save model and system prompt defaults. Storage is empty but the
              API is connected; active label: <span className="font-semibold">{activeName}</span>.
            </p>
            <Button type="button" className="mt-4" onClick={() => setCreateOpen(true)}>
              Create profile
            </Button>
          </div>
        )}

        {createOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
            <div
              className="w-full max-w-lg overflow-hidden rounded-2xl border border-white/10 shadow-2xl"
              style={{ backgroundColor: "var(--theme-bg)" }}
            >
              <div className="border-b border-white/10 px-6 py-4">
                <h3 className="text-base font-semibold">Create profile</h3>
                <p className="text-xs text-[var(--theme-muted)]">
                  Save a name, emoji, model, and system prompt.
                </p>
              </div>
              <div className="space-y-3 px-6 py-4">
                <input
                  className="w-full rounded-md border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-[var(--theme-text)]"
                  placeholder="name"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                />
                <input
                  className="w-full rounded-md border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-[var(--theme-text)]"
                  placeholder="emoji"
                  value={newEmoji}
                  onChange={(e) => setNewEmoji(e.target.value)}
                />
                <input
                  className="w-full rounded-md border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-[var(--theme-text)]"
                  placeholder="model"
                  value={newModel}
                  onChange={(e) => setNewModel(e.target.value)}
                />
                <textarea
                  className="min-h-[100px] w-full rounded-md border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-[var(--theme-text)]"
                  placeholder="System prompt"
                  value={newPrompt}
                  onChange={(e) => setNewPrompt(e.target.value)}
                />
              </div>
              <div className="flex justify-end gap-2 border-t border-white/10 px-6 py-3">
                <Button type="button" variant="secondary" onClick={() => setCreateOpen(false)}>
                  Cancel
                </Button>
                <Button
                  type="button"
                  onClick={async () => {
                    if (!newName.trim()) return;
                    setBusy("__c");
                    const { error } = await workspaceProfilesAdapter.create({
                      name: newName.trim(),
                      emoji: newEmoji || "🤖",
                      model: newModel || "ham-local",
                      systemPrompt: newPrompt,
                    });
                    setBusy(null);
                    if (error) setErr(error);
                    else {
                      setCreateOpen(false);
                      void load();
                    }
                  }}
                >
                  Create
                </Button>
              </div>
            </div>
          </div>
        )}

        {details && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
            <div
              className="w-full max-w-2xl overflow-hidden rounded-2xl border border-white/10"
              style={{ backgroundColor: "var(--theme-bg)" }}
            >
              <div className="border-b border-white/10 px-5 py-4">
                <h3 className="text-lg font-semibold">
                  {details.emoji} {details.name}
                </h3>
                <p className="text-sm text-[var(--theme-muted)]">{details.model}</p>
              </div>
              <div className="max-h-[60vh] overflow-y-auto px-5 py-4">
                <pre className="whitespace-pre-wrap font-mono text-xs text-neutral-200">
                  {details.systemPrompt || "—"}
                </pre>
              </div>
              <div className="flex justify-end border-t border-white/10 px-5 py-3">
                <Button type="button" onClick={() => setDetails(null)}>
                  Close
                </Button>
              </div>
            </div>
          </div>
        )}

        {rename && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
            <div
              className="w-full max-w-md overflow-hidden rounded-2xl border border-white/10 p-4"
              style={{ backgroundColor: "var(--theme-bg)" }}
            >
              <h3 className="text-base font-semibold">Rename profile</h3>
              <input
                className="mt-3 w-full rounded-md border border-white/10 bg-black/30 px-2 py-1.5 text-sm text-[var(--theme-text)]"
                value={renameVal}
                onChange={(e) => setRenameVal(e.target.value)}
              />
              <div className="mt-3 flex justify-end gap-2">
                <Button type="button" variant="secondary" onClick={() => setRename(null)}>
                  Cancel
                </Button>
                <Button type="button" disabled={busy === rename.id} onClick={() => void doRename()}>
                  Save
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
